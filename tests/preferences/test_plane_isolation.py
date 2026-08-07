"""The display plane imports no curation module and opens no HTTP client.

**This is the one norm whose violation looks exactly like success.** The ratified
rule is that the theme manifest file is the only channel from curation to
display; the way it gets broken is not malice but convenience — "just fetch the
label text live" — and that works perfectly in development and in every test,
because curation is up in development and in every test. A green suite is what
the violation looks like. So the guard has to be **static**: it reads the source
and holds whether or not anything is running.

**It could not have been written earlier, and had to arrive with the first module
here.** A check over an empty package passes vacuously, which is the green test
that cannot fail this repo explicitly rejects — and the window in which display
code exists unguarded is exactly the window in which the shortcut gets written.
The norm index named this file for three sessions while it did not exist; that is
recorded in `project-preferences.md` as this repo's cautionary example, and the
row moves back to `Test` naming this path because the file now does what the row
claims.

**Imports are followed transitively through this repository's own files**, which
is the difference between a guard and a formality: a direct-only check is evaded
by one shared helper, and the helper is where such an import would actually land.
Third-party packages are not followed, and that is what makes the television
exemption structural rather than a special case — `samsungtvws` reaches the set
over a websocket and drags `aiohttp` in behind it, and neither is display's
import to answer for. Talking to the television is this plane's whole job.

Both halves are proven able to fail below, against planted violations, because a
guard nobody has watched go red is a guard nobody knows is wired up.
"""

import ast
import pathlib
from collections.abc import Iterator

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DISPLAY_PACKAGE = REPOSITORY_ROOT / "display" / "src" / "display"

#: Where a module name may resolve to a file **in this repository**. Ordered by
#: how a plane's own code would find it, and **first match wins** — a name
#: present in two planes resolves to the display one, which is what an import
#: from a display module would actually get.
#:
#: That ordering cannot weaken the ban, and the reason is worth stating because
#: it is not obvious: a `curation.*` name is rejected by `_forbidden` *before*
#: resolution is ever attempted, so the guard never depends on finding the
#: curation copy of anything. Resolution exists only to keep walking repo-local
#: files, and following the display copy is the honest answer there.
SEARCH_ROOTS: tuple[pathlib.Path, ...] = (
    REPOSITORY_ROOT / "display" / "src",
    REPOSITORY_ROOT / "curation" / "src",
    REPOSITORY_ROOT,
)

#: The forbidden side of the channel. Anything under this package is curation's.
CURATION_PACKAGE = "curation"

#: HTTP clients, by the name a module would import them under. **`websockets` and
#: `samsungtvws` are deliberately absent**: the television is reached over a
#: websocket on the LAN, which is this plane's purpose and the one exemption the
#: norm names. What is banned is a *general* client, because the only thing this
#: plane could reach with one is the curation process — the second channel the
#: norm exists to prevent.
HTTP_CLIENTS: frozenset[str] = frozenset(
    {
        "aiohttp",
        "httpx",
        "requests",
        "urllib3",
        "http.client",
        "urllib.request",
        "httplib2",
        "aiohttp_client_cache",
    }
)

#: How a module smuggles an import past an AST that only reads `import` lines.
DYNAMIC_IMPORTERS: frozenset[str] = frozenset({"__import__", "import_module"})


def display_modules() -> list[pathlib.Path]:
    return sorted(DISPLAY_PACKAGE.rglob("*.py"))


def test_the_display_plane_has_modules_to_check():
    """The guard's own vacuity check.

    Everything below passes trivially over an empty package, so this is the
    assertion that says the subject exists. If the plane is ever restructured out
    from under this path, this fails loudly rather than the suite going quietly
    green over nothing.
    """
    assert display_modules(), f"no display modules under {DISPLAY_PACKAGE}; this guard would pass over nothing"


def test_no_display_module_reaches_the_curation_plane():
    offences = [offence for offence in _audit(display_modules()) if offence.kind == "curation"]

    assert offences == [], "\n".join(str(offence) for offence in offences)


def test_no_display_module_opens_an_http_client():
    offences = [offence for offence in _audit(display_modules()) if offence.kind == "http"]

    assert offences == [], "\n".join(str(offence) for offence in offences)


class TestTheGuardCanFail:
    """Planted violations, because a check never seen red is a check never wired up."""

    def test_it_catches_a_curation_import(self, tmp_path: pathlib.Path):
        module = _plant(tmp_path, "shortcut.py", "from curation.services.catalogue import CatalogueService\n")

        offences = _audit([module], roots=(tmp_path,))

        assert [offence.kind for offence in offences] == ["curation"]

    def test_it_catches_an_http_client(self, tmp_path: pathlib.Path):
        module = _plant(tmp_path, "shortcut.py", "import aiohttp\n\n\nasync def label(): return aiohttp.ClientSession()\n")

        offences = _audit([module], roots=(tmp_path,))

        assert [offence.kind for offence in offences] == ["http"]

    def test_it_catches_a_curation_import_one_helper_away(self, tmp_path: pathlib.Path):
        """The evasion the transitive half exists for.

        A direct-only check reads `shortcut.py`, sees an innocent local import,
        and passes — while the helper next to it does the forbidden thing.
        """
        _plant(tmp_path, "helper.py", "from curation.config import load\n")
        module = _plant(tmp_path, "shortcut.py", "import helper\n")

        offences = _audit([module], roots=(tmp_path,))

        assert [offence.kind for offence in offences] == ["curation"]
        assert "helper.py" in str(offences[0]), "the offence did not name the file that actually does it"

    def test_it_catches_an_http_client_one_helper_away(self, tmp_path: pathlib.Path):
        _plant(tmp_path, "helper.py", "import requests\n")
        module = _plant(tmp_path, "shortcut.py", "from helper import requests\n")

        offences = _audit([module], roots=(tmp_path,))

        assert [offence.kind for offence in offences] == ["http"]

    def test_it_catches_a_dynamically_named_client(self, tmp_path: pathlib.Path):
        """An import expressed as a string is still an import.

        Banning the `import` line and stopping there leaves `import_module` as a
        one-line hole, and the person who reaches for it is by definition working
        around the rule rather than unaware of it.
        """
        module = _plant(tmp_path, "shortcut.py", "import importlib\n\nhttp = importlib.import_module('requests')\n")

        offences = _audit([module], roots=(tmp_path,))

        assert [offence.kind for offence in offences] == ["http"]

    def test_it_does_not_object_to_the_television(self, tmp_path: pathlib.Path):
        """The exemption, asserted rather than assumed — talking to the set is the job."""
        module = _plant(
            tmp_path,
            "shortcut.py",
            "from samsungtvws.async_art import SamsungTVAsyncArt\nfrom websockets.exceptions import WebSocketException\n",
        )

        assert _audit([module], roots=(tmp_path,)) == []

    def test_a_relative_import_is_followed(self, tmp_path: pathlib.Path):
        """`from .helper import x` resolves to a file like any other name.

        Missing this is how a guard passes over a package that only ever imports
        itself relatively — which is most well-formed packages.
        """
        package = tmp_path / "plane"
        package.mkdir()
        (package / "__init__.py").write_text("")
        _plant(package, "helper.py", "import requests\n")
        module = _plant(package, "shortcut.py", "from .helper import requests\n")

        offences = _audit([module], roots=(tmp_path,))

        assert [offence.kind for offence in offences] == ["http"]


# -- the audit itself -----------------------------------------------------


class Offence:
    """One forbidden import, and the chain of files that reaches it."""

    def __init__(self, kind: str, name: str, chain: tuple[pathlib.Path, ...]) -> None:
        self.kind = kind
        self.name = name
        self.chain = chain

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        route = " -> ".join(_relative(path) for path in self.chain)
        subject = "the curation plane" if self.kind == "curation" else "an HTTP client"
        return f"{route} imports {self.name!r}, which is {subject}"


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path)


def _audit(entry_points: list[pathlib.Path], roots: tuple[pathlib.Path, ...] = SEARCH_ROOTS) -> list[Offence]:
    """Every forbidden import reachable from these files, through repo-local ones.

    Breadth-first over files rather than recursive, so a cycle between two modules
    — legal in Python and common in packages — terminates instead of recursing
    until the stack gives out.
    """
    offences: list[Offence] = []
    seen: set[pathlib.Path] = set()
    # One offence per (kind, package, file). `from curation.x import Y` yields
    # both `curation.x` and `curation.x.Y` — the resolver needs both readings,
    # since only the filesystem knows whether the tail is a submodule — but a
    # reader wants one line per place that does the forbidden thing, not one per
    # spelling of it.
    reported: set[tuple[str, str, pathlib.Path]] = set()
    queue: list[tuple[pathlib.Path, tuple[pathlib.Path, ...]]] = [(path, (path,)) for path in entry_points]

    while queue:
        path, chain = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)

        for name in _imported_names(path):
            forbidden = _forbidden(name)
            if forbidden is not None:
                kind, package = forbidden
                if (kind, package, path) not in reported:
                    reported.add((kind, package, path))
                    offences.append(Offence(kind, name, chain))
                continue
            local = _resolve(name, roots)
            if local is not None and local not in seen:
                queue.append((local, (*chain, local)))

    return offences


def _forbidden(name: str) -> tuple[str, str] | None:
    """Which rule this import breaks, if any, and the package that identifies it."""
    if name == CURATION_PACKAGE or name.startswith(f"{CURATION_PACKAGE}."):
        return ("curation", CURATION_PACKAGE)
    for client in HTTP_CLIENTS:
        if name == client or name.startswith(f"{client}."):
            return ("http", client)
    return None


def _imported_names(path: pathlib.Path) -> Iterator[str]:
    """Every module name this file imports, absolute and relative alike.

    Relative imports are resolved against the file's own package, so
    `from .helper import x` yields `plane.helper` and can be followed like any
    other name. Names passed to `import_module` or `__import__` as literals are
    yielded too — an import expressed as a string is still an import.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `_package_of` ends with the module's own stem, so the package a
                # level-1 import resolves against is everything before it — one
                # more level strips one more parent. Getting this off by one is
                # how a guard silently stops following the relative imports that
                # make up most of a well-formed package.
                base = package[: max(0, len(package) - node.level)]
                prefix = ".".join([*base, node.module] if node.module else base)
            else:
                prefix = node.module or ""
            if prefix:
                yield prefix
                for alias in node.names:
                    # `from x import y` may be importing the submodule `x.y`
                    # rather than a name inside `x`, and only the filesystem can
                    # say which — so both readings are offered to the resolver.
                    yield f"{prefix}.{alias.name}"
        elif isinstance(node, ast.Call):
            called = node.func
            name = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", None)
            if name in DYNAMIC_IMPORTERS and node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    yield node.args[0].value


def _package_of(path: pathlib.Path) -> list[str]:
    """The dotted package this file sits in, by walking up while `__init__.py` lasts."""
    parts: list[str] = []
    directory = path.parent
    while (directory / "__init__.py").is_file():
        parts.insert(0, directory.name)
        directory = directory.parent
    return [*parts, path.stem]


def _resolve(name: str, roots: tuple[pathlib.Path, ...]) -> pathlib.Path | None:
    """Where a module name lands in this repository, or None if it is third-party.

    Returning None for third-party names is what keeps the television's transport
    out of scope: `samsungtvws` imports `aiohttp`, and following into
    site-packages would report the library's own dependency as this plane's.
    """
    relative = pathlib.Path(*name.split("."))
    for root in roots:
        for candidate in (root / relative.with_suffix(".py"), root / relative / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def _plant(directory: pathlib.Path, filename: str, source: str) -> pathlib.Path:
    module = directory / filename
    module.write_text(source, encoding="utf-8")
    return module


@pytest.fixture(autouse=True)
def _guard_is_pointed_at_something_real():
    """Fails the whole module if the plane moves, rather than passing over nothing."""
    assert DISPLAY_PACKAGE.is_dir(), f"{DISPLAY_PACKAGE} does not exist; this guard has lost its subject"
