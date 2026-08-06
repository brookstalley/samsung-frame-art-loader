"""A mistyped `ART_ROOT` must report an error, not become a second collection.

Startup called `mkdir(exist_ok=True)` and then opened the catalogue, which runs
`CREATE TABLE IF NOT EXISTS`. Both steps are individually reasonable. Composed,
`ART_ROOT=/srv/atr` against a real `/srv/art` created a fresh directory, created
a fresh empty catalogue, and started cleanly — the operator got a working plane
with an empty collection and every screen agreed nothing had ever been accepted.

That is the product's own recorded "failure is silent by construction"
characteristic, in the plane written to correct it, which is why the refusal is
worth a module and a suite rather than a conditional.

The three states a directory can be in are each a test below, and so is the one
that could turn the check into an outage: a live install that predates the
marker must still start.
"""

import pytest

from curation.art_root import MARKER_NAME, ArtRootError, prepare


@pytest.fixture
def root(tmp_path):
    """A directory that is not yet an art root, and the catalogue path under it."""
    return tmp_path / "art", (tmp_path / "art" / "catalogue.sqlite")


def test_a_directory_that_is_not_an_art_root_is_refused(root):
    """The defect, stated as the behaviour that replaces it."""
    art_root, catalogue = root

    with pytest.raises(ArtRootError):
        prepare(art_root, catalogue)


def test_nothing_is_created_by_a_refusal(root):
    """The refusal must not leave behind the very thing it refused to assume.

    A check that errors *and* creates the directory would be worse than no check:
    the operator fixes the typo, and a stray empty tree is left at the mistyped
    path looking like a real one.
    """
    art_root, catalogue = root

    with pytest.raises(ArtRootError):
        prepare(art_root, catalogue)

    assert not art_root.exists()


def test_the_refusal_names_the_path_it_resolved(root):
    """The resolved path is the whole message.

    A typo is invisible in `.env` — `/srv/atr` and `/srv/art` read the same at a
    glance — and obvious the moment something reads it back. A refusal that said
    only "not an art root" would send the operator to the wrong file.
    """
    art_root, catalogue = root

    with pytest.raises(ArtRootError) as refusal:
        prepare(art_root, catalogue)

    # `ART_ROOT is <path>`, not merely the path somewhere in the message: the
    # catalogue path printed a line below *contains* the root, so a looser
    # assertion passes on a message that never names ART_ROOT at all. A sweep
    # proved it — removing the root from this sentence changed nothing.
    assert f"ART_ROOT is {art_root}" in str(refusal.value)
    assert MARKER_NAME in str(refusal.value), "the operator cannot look for a file the refusal does not name"
    assert "--init" in str(refusal.value), "a refusal with no way past it is a wall, not a check"


def test_init_creates_the_root_and_marks_it(root):
    """The one path that is allowed to create something, because it was asked to."""
    art_root, catalogue = root

    prepare(art_root, catalogue, initialise=True)

    assert (art_root / MARKER_NAME).is_file()


def test_a_marked_root_starts_without_being_asked_again(root):
    """`--init` is a once-per-deployment thing, not a flag that lives in the unit file."""
    art_root, catalogue = root
    prepare(art_root, catalogue, initialise=True)

    prepare(art_root, catalogue)


def test_a_directory_holding_a_catalogue_is_an_art_root_already(root):
    """The case that would otherwise make this check an outage on every live install.

    A directory containing this product's catalogue is an art root by better
    evidence than a marker could ever be. Refusing to start against one — because
    a file introduced later is missing — would take a working deployment down to
    enforce a rule about typos.
    """
    art_root, catalogue = root
    art_root.mkdir(parents=True)
    catalogue.write_text("not really a catalogue, but it is where one lives", encoding="utf-8")

    prepare(art_root, catalogue)


def test_an_inferred_root_is_marked_so_the_next_start_is_a_lookup(root):
    """The inference runs once, then stops being an inference.

    Left unmarked, every subsequent start would re-derive "this is a root" from
    the catalogue's presence — which is correct but is a rule that has to keep
    being true. Writing the marker makes the second start a file check.
    """
    art_root, catalogue = root
    art_root.mkdir(parents=True)
    catalogue.write_text("stand-in", encoding="utf-8")

    prepare(art_root, catalogue)

    assert (art_root / MARKER_NAME).is_file()


def test_a_marker_that_cannot_be_written_does_not_stop_a_real_root_serving(root, monkeypatch):
    """The check must not become the outage it exists to prevent.

    A read-only mount or a full disk is a real problem and it is not this one:
    the catalogue is sitting right there, so refusing to serve it because a note
    could not be left beside it would be strictly worse than the silent-typo
    defect this module was written for.
    """
    art_root, catalogue = root
    art_root.mkdir(parents=True)
    catalogue.write_text("stand-in", encoding="utf-8")
    monkeypatch.setattr(
        "curation.art_root.Path.write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read-only file system")),
    )

    prepare(art_root, catalogue)


def test_a_marker_that_is_a_directory_is_not_mistaken_for_one(root):
    """`is_file`, not `exists`. A directory of that name proves nothing.

    Pinned because the loose check reads identically at a glance and would let
    any path containing a `.curation-art-root/` entry — a stray mkdir, a
    half-restored backup — pass as a deliberate art root.
    """
    art_root, catalogue = root
    (art_root / MARKER_NAME).mkdir(parents=True)

    with pytest.raises(ArtRootError):
        prepare(art_root, catalogue)


def test_a_catalogue_path_that_is_a_directory_does_not_count_as_a_catalogue(root):
    """The same distinction on the other input, and it has the same failure.

    A directory where the catalogue should be is a broken deployment, not a
    populated one, and treating it as proof of an art root would mark a path the
    operator has never successfully run against.
    """
    art_root, catalogue = root
    catalogue.mkdir(parents=True)

    with pytest.raises(ArtRootError):
        prepare(art_root, catalogue)
