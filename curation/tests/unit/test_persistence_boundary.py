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
    # The Art Institute client — the far side of the *image* seam, the same
    # arrangement one phase down. `urllib.parse` comes with it, for percent-
    # encoding a search term into a query string; no request is made through it.
    "curation.discovery.artic",
    # `urllib.parse` only, for reading identifiers out of legacy filenames. No
    # request is made; the module is listed because the guard matches on the
    # top-level name rather than pretending to know which submodule is inert.
    "curation.seed.legacy",
    # The acquisition transport — the far side of the image-fetch seam, the same
    # arrangement as the two clients above. `direct.py` holds the ceilings, the
    # staging and the zero-byte guard and takes its stream opener as an argument,
    # which is what keeps the part worth testing exhaustively testable offline.
    "curation.acquisition.transport",
    # The fetch policy. It resolves names on purpose — deciding whether a host is
    # publicly routable is not answerable without asking what it resolves to —
    # and `urllib.parse` splits the URL. It sends no request, and its resolver is
    # an argument so the rules can be exercised against stated answers.
    "curation.acquisition.urls",
    # `urllib.parse` only, to read the host out of a citation's own URL. A
    # cited hostname and a title's last word are the same shape — `tate.org.uk`
    # and `No.5` are both dot-joined word characters — so the only thing that
    # tells them apart is whether the URL beside it names that host, and getting
    # *that* wrong merges two works under one identity. Standard parsing rather
    # than a hand-rolled split for exactly that reason. No request is made.
    "curation.discovery.dedup",
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


def test_no_test_reaches_past_the_container_to_arm_the_no_network_guard():
    """The DNS guard has to be a wiring argument, not an attribute poke.

    Every suite that touches acquisition depends on hostnames resolving to a
    fixed address, because a suite whose job is to be green cannot depend on the
    network. That guard used to be armed by assigning `acquisition._resolve`
    from the outside, which fails in the worst available direction: rename the
    attribute and the assignment still succeeds, binding a name nothing reads,
    while every acquisition test quietly starts resolving real hostnames. Green
    either way, and on hostile DNS green for the wrong reason.

    `Services.bind(resolve=...)` is the supported seam, and it fails loudly.
    This asserts nobody has gone back to the private one — including in a new
    module, which is why it greps the tree rather than naming today's two sites.

    Comments are stripped before the check, and that is not a convenience: the
    conftest comment explaining *why* the assignment was abandoned names the old
    form verbatim, and a guard that forbids describing the mistake it prevents
    would be paid for by deleting the explanation.
    """
    scanned = list((_SOURCE_ROOT.parent / "tests").rglob("*.py"))
    offenders = [
        f"{path.relative_to(_SOURCE_ROOT.parent)}:{number}"
        for path in scanned
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if "._resolve" in (code := line.split("#", 1)[0]) and "=" in code.split("._resolve", 1)[1][:3]
    ]

    # A guard that scans nothing passes forever, and this one is a path away from
    # scanning nothing — move the tree and `rglob` returns empty rather than
    # failing. Its two siblings in this module assert the same thing for the same
    # reason.
    assert scanned, "the test tree moved; this guard was scanning nothing"
    assert offenders == [], f"arm the no-network guard with Services.bind(resolve=...), not by assignment: {offenders}"


# -- the generic tier reaches neither domain -----------------------------------


#: The modules allowed to import a domain adapter, and why each one is.
#:
#: **An allowlist, not a list of guarded files, and the direction is the whole
#: point** — the same reasoning the network guard below states. Naming what is
#: *guarded* stops covering whatever is added next, silently, and its result looks
#: identical either way: the first version of this guard named two modules as "the
#: generic tier" and `adapter.py` was not one of them, so a
#: `from curation.persistence.catalogue import …` there would have gone uncaught.
#: Adding it fixed that instance and nothing else; a sweep then showed that
#: removing any name from the set was itself uncaught, because nothing asserted
#: what the set contained. Inverted, every module under `persistence/` is covered
#: the day it is written and an exception has to be argued for here.
_MAY_IMPORT_A_DOMAIN_ADAPTER = {
    # The adapters themselves: a module cannot reach through itself.
    "curation.persistence.catalogue",
    "curation.persistence.sqlite_discovery",
    # One open file serves both domains, and this is what opens it — so it holds
    # the discovery schema marker as well as the catalogue's.
    "curation.persistence.file",
}

#: The two domain adapters. Everything beneath them is generic by construction:
#: `durable.py` states it "holds no artwork, artist or theme concept", and
#: `adapter.py` opens "what a domain adapter over the durable store does the same
#: way every time".
_DOMAIN_ADAPTERS = {"curation.persistence.catalogue", "curation.persistence.sqlite_discovery"}


def _imports_any(tree: ast.AST, modules: set[str]) -> set[str]:
    """Which of `modules` this module binds, plain or `from`-style."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name in modules}
        elif isinstance(node, ast.ImportFrom):
            if node.module in modules:
                found.add(node.module)
    return found


def offending_importers(reached_by: dict[str, set[str]], allowed: set[str]) -> dict[str, list[str]]:
    """Which modules import a domain adapter without being allowed to.

    Extracted so the allowlist's *strictness* can be shown, which reading the
    real tree cannot do: every module here is either allowed or importing
    nothing, so the check can only ever be watched passing. A sweep replaced the
    membership test with `if True` — skipping every module — and nothing went
    red. That is the fourth guard in this tree to fail the same way, which is why
    the fabricated cases below exist rather than a comment saying it looks right.
    """
    return {name: sorted(reached) for name, reached in reached_by.items() if reached and name not in allowed}


def test_nothing_beneath_the_domain_adapters_imports_one():
    """`durable.py` says it holds no domain concept; every module below has to agree.

    It reached *through* `catalogue.py` — the module declaring `CatalogueStore` —
    for `StorageError` and `StoreMisuseError`, so the tier beneath both adapters
    depended on one of the two domains it serves. Nothing was broken and nothing
    was mis-ordered at import: it was a layering statement the code contradicted
    in one line, which is exactly the kind that survives every behavioural test
    and every reading of the module that states it.

    The types now live in `persistence/errors.py`, which neither domain owns, and
    this is what stops the import creeping back — into that module or into any
    other, including ones not yet written.
    """
    modules = sorted((_SOURCE_ROOT / "curation" / "persistence").glob("*.py"))
    assert modules, "no persistence modules found — this guard would pass vacuously"
    assert _DOMAIN_ADAPTERS, "no domain adapters named — every module imports none of nothing"
    for adapter in sorted(_DOMAIN_ADAPTERS):
        assert (_SOURCE_ROOT / (adapter.replace(".", "/") + ".py")).is_file(), (
            f"{adapter} is named as a domain adapter and does not exist — a rename would empty "
            "this check without emptying the set, which reads identically to passing"
        )

    reached_by = {
        _module_name(path): _imports_any(ast.parse(path.read_text(encoding="utf-8")), _DOMAIN_ADAPTERS) for path in modules
    }
    offenders = offending_importers(reached_by, _MAY_IMPORT_A_DOMAIN_ADAPTER)

    assert not offenders, (
        f"these modules sit beneath the domain adapters and import one: {offenders}. "
        "Shared types belong in persistence/errors.py, which neither domain owns. If the import "
        f"is genuinely right, add the module to _MAY_IMPORT_A_DOMAIN_ADAPTER with its reason."
    )


def test_every_allowed_importer_still_exists():
    """An allowlist entry for a deleted module is an exemption nobody is using.

    Left behind, it silently pre-approves whatever takes that name next — which
    is the failure an allowlist trades for the one it fixes, and the only one it
    has.
    """
    for name in sorted(_MAY_IMPORT_A_DOMAIN_ADAPTER):
        path = _SOURCE_ROOT / (name.replace(".", "/") + ".py")
        assert path.is_file(), f"{name} is allowed to import a domain adapter and does not exist"


def test_the_catalogue_still_re_exports_the_shared_error_types():
    """Moving them must not break `except StorageError` on a catalogue import.

    `CatalogueStore`'s own methods raise these, so a caller holding a catalogue
    store should not have to know which module declared the class to catch it.
    The re-export is deliberate and permanent rather than a transitional shim, so
    it is asserted rather than left to be tidied away by someone reading it as one.
    """
    from curation.persistence import catalogue, errors  # noqa: PLC0415

    assert catalogue.StorageError is errors.StorageError
    assert catalogue.StoreMisuseError is errors.StoreMisuseError


def test_a_module_reaching_a_domain_adapter_is_reported():
    """The case the real tree cannot produce, because the real tree is correct."""
    offenders = offending_importers(
        {"curation.persistence.durable": {"curation.persistence.catalogue"}},
        allowed=set(),
    )

    assert offenders == {"curation.persistence.durable": ["curation.persistence.catalogue"]}


def test_an_allowed_module_reaching_a_domain_adapter_is_not_reported():
    """The allowlist has to actually excuse something, or it is decoration."""
    assert not offending_importers(
        {"curation.persistence.file": {"curation.persistence.sqlite_discovery"}},
        allowed={"curation.persistence.file"},
    )


def test_a_module_importing_nothing_is_not_reported():
    """An empty reach is not an offence — the common case, and the one a `not reached`
    check inverted would flag on every module in the package."""
    assert not offending_importers({"curation.persistence.records": set()}, allowed=set())
