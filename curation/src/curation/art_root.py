"""Whether a directory is the art root, or a typo that would become one.

**Two individually reasonable steps composed into a silent failure.** Startup
called `art_root.mkdir(parents=True, exist_ok=True)` and then opened the
catalogue, which runs `CREATE TABLE IF NOT EXISTS`. So a mistyped `ART_ROOT`
created a fresh directory, created a fresh empty catalogue, and started cleanly:
the operator got a working plane with an empty collection instead of an error,
and every screen agreed that nothing had ever been accepted.

That lands exactly on this product's recorded "failure is silent by construction"
characteristic — the thing it exists to correct — so a plane that self-heals into
an empty install is the defect closest to home.

**The fix is a marker, and the point of a marker is that a typo cannot have one.**
An art root is a directory somebody deliberately made one. `ART_ROOT=/mnt/phtoos`
against a real `/mnt/photos` finds no marker and refuses, naming both the path it
resolved and the way to say "yes, really, make this one". *(The illustration is
deliberately not this deployment's own path: naming it here would both go stale
the day the tree moves and trip the guard that keeps deployment values out of
source, which is a norm this file has no business being the exception to.)*

**A directory already holding a catalogue counts as marked**, and that is not a
grandfather clause bolted on: a directory containing this product's catalogue file
is an art root by the only evidence that could ever matter, and refusing to start
against one would turn a safety check into an outage on every existing install.
The marker is written when that path is taken, so the second start is decided by
the marker rather than by the inference.

Nothing here creates anything unless asked. `prepare` is the whole surface, and
the only path that writes is the one the operator asked for with `--init` or the
one where a catalogue already proves the answer.
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

#: Written inside the art root, and looked for there. A dotfile because it is
#: bookkeeping rather than content: the root's other entries are directories a
#: curator may reasonably browse.
MARKER_NAME = ".curation-art-root"

#: What goes in it. Not parsed — nothing reads this back — so it is written for
#: the person who finds the file and wonders what it is, which is the only
#: audience it has.
MARKER_TEXT = (
    "This directory is a curation art root.\n"
    "\n"
    "The curation plane refuses to start against a directory that has neither this\n"
    "file nor a catalogue, so that a mistyped ART_ROOT reports an error instead of\n"
    "quietly creating a second, empty collection. Delete this file only if you mean\n"
    "to stop this directory being an art root.\n"
)


class ArtRootError(RuntimeError):
    """The configured art root is not one, and was not asked to become one."""


def prepare(art_root: Path, catalogue_path: Path, *, initialise: bool = False) -> None:
    """Make sure `art_root` is a deliberate art root, or refuse to start.

    Ordered so the cheapest certain answer comes first and nothing is created
    before the decision is made:

    1. The marker is there — this is a root, proceed.
    2. A catalogue is there — this is a root by better evidence than a marker,
       so proceed *and* write the marker, which makes the next start a lookup
       rather than an inference.
    3. `initialise` — the operator said to make one, so make one.
    4. Otherwise refuse, naming the resolved path. The path is the whole message:
       a typo is invisible in `.env` and obvious the moment something reads it
       back.
    """
    marker = art_root / MARKER_NAME
    if marker.is_file():
        return

    if catalogue_path.is_file():
        log.info(
            "art root %s holds a catalogue but no marker; marking it, so a future start is decided by the marker",
            art_root,
            extra={"event": "art_root.marked", "art_root": str(art_root)},
        )
        _write_marker(marker)
        return

    if initialise:
        art_root.mkdir(parents=True, exist_ok=True)
        _write_marker(marker)
        log.info(
            "created a new, empty art root at %s",
            art_root,
            extra={"event": "art_root.created", "art_root": str(art_root)},
        )
        return

    raise ArtRootError(
        f"ART_ROOT is {art_root}, which is not a curation art root: it holds neither {MARKER_NAME} "
        f"nor a catalogue at {catalogue_path}.\n"
        "\n"
        "If that path is a typo, fix ART_ROOT in .env — this refusal is the whole point, because "
        "starting anyway would create an empty collection that looks healthy and is not yours.\n"
        "\n"
        "If you really do mean to start a new, empty collection there, run it once with --init:\n"
        "    uv run python -m curation --init"
    )


def _write_marker(marker: Path) -> None:
    """Write the marker, and do not fail startup if it cannot be written.

    A read-only or full disk is a real problem and it is not *this* one: the
    directory has already proved it is an art root, and refusing to serve a
    catalogue that is sitting right there because a note could not be left beside
    it would be the check causing the outage it exists to prevent. It is said out
    loud rather than swallowed, so the next start refusing is explicable.
    """
    try:
        marker.write_text(MARKER_TEXT, encoding="utf-8")
    except OSError as exc:
        log.warning(
            "could not write the art-root marker at %s (%s); this start is unaffected, but a later one "
            "will have to re-infer the root from the catalogue",
            marker,
            exc,
            extra={"event": "art_root.marker_unwritable"},
        )
