"""The storage driver stays inside the persistence package.

The catalogue is reached only through the service layer, and the whole point of
splitting persistence into a durable store and a domain adapter is that the layers
above bind to what the catalogue can be asked, not to how one file answers it. A
stray `import sqlite3` in a service or an MCP binding would undo that quietly: the
code would work, every behavioural test would pass, and the seam would be gone.

The failure mode is invisible by construction, so it gets a mechanical guard
rather than vigilance — the same reason `tests/test_repo_hygiene.py` exists.
"""

import ast
import pathlib

#: Modules that may bind to the storage driver directly. Everything else reaches
#: storage through the `CatalogueStore` contract.
_MAY_IMPORT_SQLITE = {"curation.persistence.durable"}

_DRIVER = "sqlite3"
_SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"


def _module_name(path: pathlib.Path) -> str:
    parts = path.relative_to(_SOURCE_ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports_driver(tree: ast.AST) -> bool:
    """Whether this module binds `sqlite3` at any level, plain or `from`-style."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == _DRIVER for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            # `node.module` is None for a relative import, which cannot be stdlib.
            if node.module is not None and node.module.split(".")[0] == _DRIVER:
                return True
    return False


def test_only_the_durable_store_imports_the_storage_driver():
    modules = sorted(_SOURCE_ROOT.rglob("*.py"))
    assert modules, f"No modules found under {_SOURCE_ROOT}; this guard would pass vacuously."

    offenders = sorted(_module_name(path) for path in modules if _imports_driver(ast.parse(path.read_text(encoding="utf-8"))))

    assert set(offenders) <= _MAY_IMPORT_SQLITE, (
        f"{_DRIVER!r} is imported outside the durable store by: {', '.join(sorted(set(offenders) - _MAY_IMPORT_SQLITE))}. "
        "Reach storage through the CatalogueStore contract, or add the module here with a reason."
    )


# -- discovery reaches nothing, and that is structural --------------------------


#: Modules permitted to reach the network. Everything else in the package is
#: guarded, which is the only direction that stays correct as the tree grows: a
#: list of *guarded* files silently stops covering whatever is added next, and
#: its result looks identical either way.
_MAY_REACH_THE_NETWORK = {
    # The OpenRouter client — the far side of the engine seam, which is exactly
    # where a transport belongs.
    "curation.discovery.openrouter",
    # `urllib.parse` only, for reading identifiers out of legacy filenames. No
    # request is made; the module is listed because the guard matches on the
    # top-level name rather than pretending to know which submodule is inert.
    "curation.seed.legacy",
}

_REACHES_THE_NETWORK = {"httpx", "requests", "urllib", "urllib3", "http", "socket", "aiohttp", "openai", "anthropic"}


def _imported_roots(tree: ast.AST) -> set[str]:
    """Every top-level package this module binds, plain or `from`-style."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_client_beyond_the_engine_seam_can_reach_the_network():
    """The seam exists so the run lifecycle is buildable without a paid API.

    That claim is worth a mechanism rather than a promise: the run lifecycle
    drives a state machine over a local file, and the first HTTP client imported
    into it would turn every test of that lifecycle into one that quietly depends
    on a network — passing on a developer's machine and failing on a build host,
    or worse, spending money.

    **Stated as an allowlist over the whole package, not as a list of guarded
    files.** It was the latter until 2026-08-02, naming three modules chosen when
    those three were the whole of discovery; a phase-2 engine added above the seam
    would have been unguarded, and the guard would have gone on passing with no
    sign that its scope no longer matched the tree. A guard's effective scope has
    to be visible in its result, and the only formulation with that property is
    the one that covers everything by default. Its sibling above already worked
    this way.
    """
    modules = sorted(_SOURCE_ROOT.rglob("*.py"))
    assert modules, f"No modules found under {_SOURCE_ROOT}; this guard would pass vacuously."

    offenders = {
        _module_name(path): sorted(_imported_roots(ast.parse(path.read_text(encoding="utf-8"))) & _REACHES_THE_NETWORK)
        for path in modules
    }
    offenders = {name: hits for name, hits in offenders.items() if hits and name not in _MAY_REACH_THE_NETWORK}

    assert not offenders, (
        "these modules can reach the network and are not on the allowlist: "
        + "; ".join(f"{name} imports {hits}" for name, hits in sorted(offenders.items()))
        + ". A transport belongs beyond the engine seam — add it to _MAY_REACH_THE_NETWORK only with a reason."
    )
