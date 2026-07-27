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
