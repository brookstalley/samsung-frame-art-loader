"""Opening the one file both halves of the model live in.

The catalogue and the pre-acceptance pipeline are separate concerns with separate
contracts and separate adapters, and they share a single SQLite file on purpose.
Acceptance is a promotion — a candidate work becomes an Artwork and its image
instances become that work's Sources — which writes on both sides and has to
commit once or not at all. Two connections cannot do that, so there is one, and
this is where it is opened with every table either adapter will ask for.

A schema fragment omitted here is not a subtle failure: the durable store
validates identifiers against the schema the file actually declares, so an
adapter reaching for a table nobody created is refused by name on its first call.
"""

from functools import partial
from pathlib import Path

from curation.persistence.durable import SqliteDurableStore
from curation.persistence.migrations import DEFAULT_WALL_NAME, establish_the_wall
from curation.persistence.sqlite import CATALOGUE_SCHEMA
from curation.persistence.sqlite_discovery import DISCOVERY_SCHEMA


def open_catalogue_file(path: Path | str, *, wall_name: str = DEFAULT_WALL_NAME) -> SqliteDurableStore:
    """Open the catalogue file, creating whatever tables it does not yet have.

    The caller owns closing it. Both adapters are views over the returned store
    rather than owners of it, so there is exactly one place the connection is
    released.

    **`wall_name` is used only when this file has no wall at all** — on a fresh
    catalogue, and on the one-time move of a single-wall file onto the per-wall
    shape. A wall that exists keeps the name it has, because by then the name is
    the curator's rather than the deployment's; nothing here renames one. The
    default is what a deployment that has said nothing gets.
    """
    return SqliteDurableStore(
        path,
        CATALOGUE_SCHEMA + DISCOVERY_SCHEMA,
        migrations=(partial(establish_the_wall, wall_name=wall_name),),
    )
