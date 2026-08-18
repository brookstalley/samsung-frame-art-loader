"""`information-architecture.md`'s per-screen tables describe the screens that exist.

The artifact describes the curation surface in three per-screen tables —
§ Screen Inventory, § Information Hierarchy and § Screen States — plus a
one-sentence enumeration of the contextual screens in § Navigation Structure.
All four are supposed to agree with `app.js`'s route table, which is the surface's
own list of every screen it can show.

**This file exists because the rule that was supposed to hold them together is a
rule asking a human to read two lists against each other, and it has now failed
three times in the same artifact.** § Information Hierarchy states it outright —
"One row here per screen in § Screen Inventory, and the agreement is the check" —
and records that the agreement was last restored a chunk after the screens
shipped, when Critic review put the two side by side (#123). #148 then found the
same shape twice more: a Run screen routed and in none of the three tables, and a
§ Screen States table claiming to assess every screen while carrying seven of ten.

The drift is invisible per-chunk. A chunk that adds a screen adds it where the
work is, and the artifact's tables are three scrolls away in a different project's
directory; nothing about that chunk's diff looks wrong. That is the class of
failure a test catches and a reading does not, which is why the rule keeps its
sentence — it still says what agreement *means* — and loses its job to this file.

It reads both sources rather than importing either, the technique
`test_plane_isolation.py` and `test_heartbeat_contract.py` already use, and it
lives in the root suite because the two files it compares are in two different
projects: `.prawduct/artifacts/` is the repository's and `app.js` is the curation
plane's, and neither plane's suite spans both.

The guard is proven able to fail below, in both directions, because a check
nobody has watched go red is a check nobody knows is wired up — and shipping an
unwatched check *here*, in the file whose whole subject is an unenforced rule,
would be the sharpest possible way to repeat the defect.
"""

import pathlib
import re
import sys

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ROUTE_TABLE = REPOSITORY_ROOT / "curation" / "src" / "curation" / "http" / "static" / "app.js"
ARTIFACT = REPOSITORY_ROOT / ".prawduct" / "artifacts" / "information-architecture.md"

#: The three tables, by the section heading each lives under. Every one of them
#: carries one row per screen, and the first column is the screen's name.
TABLE_SECTIONS = ("Screen Inventory", "Information Hierarchy", "Screen States")

#: What each route key is called in the artifact's prose.
#:
#: The two lists cannot be compared without it: the route table keys on `walls`
#: and the artifact writes "The Walls", because one is an identifier and the
#: other is a name a curator reads. Declared here rather than derived by
#: title-casing, which would map `walls` to "Walls" and miss the article.
#:
#: **A route with no entry here fails `test_every_route_has_a_name`**, so this
#: mapping cannot silently fall behind the route table the way the tables it
#: exists to check did. Adding a screen means adding a line here, and the test
#: says so when you have not.
SCREEN_NAMES = {
    "walls": "The Walls",
    "collection": "Collection",
    "discover": "Discover",
    "work": "Work",
    "run": "Run",
    "conversation": "Conversation",
    "review": "Review",
    "theme": "Theme",
    "taste": "Taste",
    "health": "Health",
}


def _without_comments(source: str) -> str:
    """`/* … */` and `//…` gone, their newlines kept so brace matching still works."""
    source = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group().count("\n"), source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def routes() -> dict[str, str]:
    """Every entry in `app.js`'s `ROUTES`, as `{key: its literal body}`.

    Brace-matched rather than line-matched: the entries carry comments between
    them and object literals inside them, and a regex over lines would either
    miss a key whose value wrapped or invent one from a comment. Only depth-1
    keys count, which is what makes a nested `{ … }` in an entry's body
    invisible here.

    Parsed rather than executed. Running the client's module to ask it would
    need a browser — `app.js` imports ten screens and calls `install()` at
    import time — and the point is to read what the file says.

    **Comments are stripped before anything is read, and that is load-bearing.**
    The table is heavily commented and the prose discusses the very keys this
    parses: the note above `conversation` calls it "contextual rather than a
    fourth destination:", which read as a `destination:` field and made a
    contextual screen parse as a fourth destination.
    """
    source = _without_comments(ROUTE_TABLE.read_text(encoding="utf-8"))
    start = source.index("const ROUTES = {") + len("const ROUTES = ")
    depth = 0
    for offset in range(start, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                body = source[start + 1 : offset]
                break
    else:  # pragma: no cover - an unbalanced literal is a syntax error upstream
        raise AssertionError(f"{_relative(ROUTE_TABLE)} has an unbalanced ROUTES literal")

    found: dict[str, str] = {}
    depth = 0
    key = None
    entry_start = 0
    for offset, character in enumerate(body):
        if character == "{":
            if depth == 0:
                head = body[entry_start:offset]
                match = re.search(r"(\w+)\s*:\s*$", head)
                key = match.group(1) if match else None
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                if key is not None:
                    found[key] = body[entry_start:offset]
                entry_start = offset + 1
                key = None
    return found


def section(heading: str) -> str:
    """One `##` section's body, up to the next heading of the same level."""
    source = ARTIFACT.read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## )", source, re.MULTILINE | re.DOTALL)
    assert match is not None, f"{_relative(ARTIFACT)} has no '## {heading}' section"
    return match.group(1)


def screens_in_table(heading: str) -> list[str]:
    """The first column of every data row of the table in a section.

    The header row and its `|---|` rule are dropped, and so is any emphasis the
    name carries: § Screen Inventory bolds its names and marks two of them
    `*(new)*`, and none of that is part of the screen's identity.
    """
    names = []
    for line in section(heading).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cell = line.split("|")[1].strip()
        if not cell or set(cell) <= {"-", ":"} or cell == "Screen":
            continue
        cell = re.sub(r"\*\([^)]*\)\*", "", cell)
        names.append(cell.replace("*", "").strip())
    return names


def contextual_screens() -> set[str]:
    """The names § Navigation Structure's `**Contextual:**` bullet enumerates.

    The sentence's shape is the contract this parses — a bullet beginning
    `- **Contextual:**` whose names run up to "are reached". Stated here because
    a rewrite that keeps the meaning and loses the shape turns this check off,
    and a check that silently stops checking is worse than the reading it
    replaced.
    """
    # Whitespace is collapsed before matching because the bullet wraps, and it
    # wraps *inside* the phrase being matched — "are\n  reached" is one span to
    # a reader and two lines to a regex.
    body = " ".join(section("Navigation Structure").split())
    match = re.search(r"- \*\*Contextual:\*\*(.*?)are reached", body)
    assert match is not None, "§ Navigation Structure has no '- **Contextual:** … are reached' sentence"
    # Drop the lead-in clause before the enumeration proper ("everything else.").
    sentence = match.group(1).rsplit(".", 1)[-1]
    return {name.strip() for name in re.split(r",|\band\b", sentence) if name.strip()}


def _relative(path: pathlib.Path) -> str:
    return str(path.relative_to(REPOSITORY_ROOT))


def test_both_sources_exist_to_be_compared():
    """The vacuity check: every assertion below passes trivially over a typo'd path."""
    assert ROUTE_TABLE.is_file(), f"nothing at {_relative(ROUTE_TABLE)} to read the routes from"
    assert ARTIFACT.is_file(), f"nothing at {_relative(ARTIFACT)} to read the tables from"


def test_the_route_table_parses():
    """A parser that silently matched nothing would make every check below green.

    Pinned against the three destinations rather than a count: those three are
    `information-architecture.md` § Direction's ratified navigation and the one
    part of this table that is not free to change quietly.
    """
    found = routes()
    assert {"walls", "collection", "discover"} <= set(found), (
        f"{_relative(ROUTE_TABLE)} parsed as {sorted(found)}, which is missing a destination — "
        "the parser is reading the wrong thing"
    )
    destinations = [key for key, body in found.items() if "destination:" in body]
    assert destinations == ["walls", "collection", "discover"], (
        f"the navigation's destinations are {destinations}. "
        "§ Direction ratifies three, named for what a curator does rather than for a pipeline stage"
    )


def test_every_route_has_a_name():
    """`SCREEN_NAMES` covers the route table, so no screen falls out of the comparison."""
    unnamed = sorted(set(routes()) - set(SCREEN_NAMES))
    assert not unnamed, (
        f"{unnamed} are routed in {_relative(ROUTE_TABLE)} and have no entry in SCREEN_NAMES. "
        "Add one per screen — without it the screen is invisible to every check in this file"
    )
    unrouted = sorted(set(SCREEN_NAMES) - set(routes()))
    assert not unrouted, f"SCREEN_NAMES carries {unrouted}, which {_relative(ROUTE_TABLE)} does not route"


@pytest.mark.parametrize("heading", TABLE_SECTIONS)
def test_every_screen_has_a_row(heading: str):
    expected = {SCREEN_NAMES[key] for key in routes()}
    listed = set(screens_in_table(heading))

    missing = sorted(expected - listed)
    assert not missing, (
        f"§ {heading} has no row for {missing}, which {_relative(ROUTE_TABLE)} routes. "
        "A screen with no row is a screen the design does not describe"
    )


@pytest.mark.parametrize("heading", TABLE_SECTIONS)
def test_every_row_is_a_screen(heading: str):
    """The other direction: a row describing a screen that no longer exists.

    Its failure is quieter than the missing-row one and worse to read — prose
    describing a screen nobody can reach looks exactly like prose describing a
    screen you have not found yet.
    """
    expected = {SCREEN_NAMES[key] for key in routes()}
    extra = sorted(set(screens_in_table(heading)) - expected)
    assert not extra, (
        f"§ {heading} has rows for {extra}, which {_relative(ROUTE_TABLE)} does not route. "
        "Either the screen was removed and its row outlived it, or the row names it differently than SCREEN_NAMES does"
    )


def test_the_contextual_enumeration_matches_the_route_table():
    """A contextual screen is one reached from a destination, and returns to it.

    Derived from the route table's own shape — an `opensFrom` and no
    `destination` — rather than from a second hand-kept list. Health is excluded
    because § Navigation Structure excludes it in its own bullet, deliberately:
    it is reachable and not navigable-to, and the masthead indicator is what
    makes that demotion safe.
    """
    contextual = {
        SCREEN_NAMES[key]
        for key, body in routes().items()
        if "opensFrom:" in body and "destination:" not in body and key != "health"
    }
    assert contextual_screens() == contextual, (
        f"§ Navigation Structure enumerates {sorted(contextual_screens())}; "
        f"the route table's contextual screens are {sorted(contextual)}"
    )


class TestTheGuardCanFail:
    """Planted violations, both directions, over the real parsers.

    The route table is replaced and the artifact is left real, so each plant
    fails for the reason it names rather than for the drift the rest of this
    file is about. `sys.modules[__name__]` rather than a dotted string: there is
    no `__init__.py` under `tests/preferences/`, so a string target imports a
    *second* copy of this module and patches that one — which leaves these three
    passing on the real check's own failure and proves nothing.
    """

    def test_it_catches_a_table_missing_a_screen(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(SCREEN_NAMES, "invented", "Invented")
        monkeypatch.setattr(sys.modules[__name__], "routes", lambda: {"invented": "{ render: viewInvented }"})
        with pytest.raises(AssertionError, match="has no row for"):
            test_every_screen_has_a_row("Screen Inventory")

    def test_it_catches_a_row_for_a_screen_that_is_not_routed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.modules[__name__], "routes", lambda: {"walls": "{ destination: 'The Walls' }"})
        with pytest.raises(AssertionError, match="has rows for"):
            test_every_row_is_a_screen("Screen Inventory")

    def test_it_catches_a_route_nobody_named(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.modules[__name__], "routes", lambda: {"walls": "{}", "unnamed": "{}"})
        with pytest.raises(AssertionError, match="no entry in SCREEN_NAMES"):
            test_every_route_has_a_name()

    def test_it_catches_a_contextual_enumeration_that_drifted(self, monkeypatch: pytest.MonkeyPatch):
        """The fourth surface, and the one #148 found drifted with the tables."""
        monkeypatch.setattr(
            sys.modules[__name__],
            "routes",
            lambda: {"walls": "{ destination: 'x' }", "work": "{ opensFrom: 'collection' }"},
        )
        with pytest.raises(AssertionError, match="enumerates"):
            test_the_contextual_enumeration_matches_the_route_table()

    def test_the_comment_stripper_does_not_eat_the_code(self):
        """It runs over every read of the route table, so its own failure is silent."""
        assert _without_comments("a: 1, // destination: no\nb: 2\n") == "a: 1, \nb: 2\n"
        assert _without_comments("/* a\nfourth destination: */\nkeep") == "\n\nkeep"

    def test_the_table_parser_reads_a_real_row(self):
        """So the row parsers are known to return something before they are trusted."""
        assert "The Walls" in screens_in_table("Screen Inventory")
        assert "Screen" not in screens_in_table("Screen Inventory")

    def test_the_row_parser_strips_emphasis_and_notes(self):
        """§ Screen Inventory bolds every name and marks two of them `*(new)*`."""
        inventory = screens_in_table("Screen Inventory")
        assert "Conversation" in inventory, f"emphasis or a note survived normalisation: {inventory}"
