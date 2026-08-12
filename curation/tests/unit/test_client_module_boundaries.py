"""The client's module boundaries, asserted rather than agreed to.

The browser client is a tree of ES modules: `app.js` holds boot and the route
table, `core/` holds what every screen shares, and `screens/` holds one module per
screen. The rule that makes the tree worth having is recorded in
`architecture.md` § Components & Responsibilities:

    No module under `screens/` imports another. They meet in `core/` and in the
    route table.

**Why it earns a test where the Direction norm beside it does not.** That norm's
violation — a destination named for a pipeline stage rather than an intention —
has no import signature and no grep, so its enforcement is the Critic's
judgement. This one is exactly an import, which makes it the cheap half to
mechanise: a screen reaching sideways into another rebuilds the single-writer
file the split exists to end, and it does so one plausible-looking import at a
time, in a diff that reads fine on its own.
"""

import re

from curation.http.pages import STATIC_DIR

CORE = STATIC_DIR / "core"
SCREENS = STATIC_DIR / "screens"

#: A static `import … from "<specifier>"` or a dynamic `import("<specifier>")`.
#: Both, because a screen smuggled in behind a lazy import is the same coupling.
IMPORT = re.compile(r"""\bimport\s*(?:[\s\S]*?\bfrom\s*)?\(?\s*["']([^"']+)["']""")


def _imports(source: str) -> list[str]:
    return IMPORT.findall(source)


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_tree_the_rule_is_about_actually_exists():
    """A rule checked against an empty directory passes and means nothing."""
    assert sorted(p.name for p in CORE.glob("*.js")), "core/ holds no modules"
    assert sorted(p.name for p in SCREENS.glob("*.js")), "screens/ holds no modules"


def test_no_screen_imports_another_screen():
    """The acceptance criterion, and the property a later wave's agents depend on.

    Four agents can build four screens at once only while each owns one file. A
    screen that reaches into another makes the second agent a reader of the
    first's uncommitted work, which is the queue this split converted into waves.
    """
    for module in sorted(SCREENS.glob("*.js")):
        sideways = [
            specifier
            for specifier in _imports(_read(module))
            # A relative specifier that does not climb out of `screens/` is a
            # sibling; `../core/...` is the sanctioned direction.
            if specifier.startswith("./") or "/screens/" in specifier
        ]
        assert not sideways, f"screens/{module.name} imports {sideways}; screens meet in core/, never each other"


def test_no_core_module_imports_a_screen():
    """The same rule from the other side, and the one that makes `core/` shared.

    A `core/` module that reached into a screen would make every other screen
    depend on that one transitively — the split undone, and undone invisibly,
    because nothing in `screens/` would look wrong.
    """
    for module in sorted(CORE.glob("*.js")):
        upward = [specifier for specifier in _imports(_read(module)) if "screens/" in specifier]
        assert not upward, f"core/{module.name} imports {upward}; core knows no screen"


def test_every_screen_module_is_reachable_from_the_route_table():
    """A screen nobody routes to is dead code that still has to be maintained.

    Read off `app.js` because that is where the plan puts the table, and it is
    the one place a screen becomes reachable at all.
    """
    boot = _read(STATIC_DIR / "app.js")
    imported = {specifier.rsplit("/", 1)[-1] for specifier in _imports(boot) if "screens/" in specifier}
    on_disk = {module.name for module in SCREENS.glob("*.js")}

    assert on_disk, "screens/ holds no modules, so this check would pass vacuously"
    assert on_disk - imported == set(), f"{sorted(on_disk - imported)} are in screens/ and reachable from nowhere"
