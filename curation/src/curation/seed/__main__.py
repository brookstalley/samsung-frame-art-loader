"""Seed the catalogue from the 2024 index: `uv run python -m curation.seed <index>`.

Hand-run and one-shot, which is why its report goes to stdout rather than only to
the journal: the point of running it is to read what it says. The report itself
is a value built by `ingest`, and this module only sets it in text — so what the
run found can be asserted on without capturing output.

The index path is an argument rather than a setting because the file is not part
of the art tree and has no fixed home: it belongs to the checkout of the 2024
code that produced it.
"""

import argparse
import logging
import sys
from pathlib import Path

from curation import logs
from curation.config import Settings
from curation.persistence.file import open_catalogue_file
from curation.persistence.sqlite import SqliteCatalogue
from curation.seed.ingest import SeedReport, seed_catalogue
from curation.seed.legacy import LegacyIndexError, read_index
from curation.services.catalogue import CatalogueService


def main(argv: list[str] | None = None) -> int:
    """Read the index, seed the catalogue, print what happened."""
    # The same shape the serving entry point installs. Two entry points into one
    # plane emitting two log formats is a journal that has to be read two ways,
    # and the one that ingests the whole 2024 corpus is not the one to leave out.
    logs.configure(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="python -m curation.seed", description=__doc__.splitlines()[0])
    parser.add_argument("index", type=Path, help="the 2024 index file, normally all.json in the legacy checkout")
    arguments = parser.parse_args(argv)

    settings = Settings.from_env()
    try:
        records = read_index(arguments.index)
    except (LegacyIndexError, OSError) as exc:
        # Named rather than raised: a mistyped path is the most likely way to
        # reach this line, and a traceback would bury that behind a stack.
        print(f"Could not read {arguments.index}: {exc}", file=sys.stderr)  # noqa: T201 -- the report is this tool's output
        return 2

    settings.art_root.mkdir(parents=True, exist_ok=True)
    catalogue_file = open_catalogue_file(settings.catalogue_path, wall_name=settings.wall_name)
    try:
        # The catalogue service and nothing else: seeding writes works, artists,
        # sources, images and mats, and touches neither discovery state nor the
        # standing directive — so it needs neither of the services that own them,
        # nor the startup reconciliation that repairs them.
        report = seed_catalogue(
            records,
            catalogue=CatalogueService(SqliteCatalogue(catalogue_file)),
            art_root=settings.art_root,
        )
    finally:
        catalogue_file.close()

    for line in render(report, art_root=settings.art_root):
        print(line)  # noqa: T201 -- the report is this tool's output
    return 0


def render(report: SeedReport, *, art_root: Path) -> list[str]:
    """The report as a person reads it, worst news first.

    Returned as lines rather than printed so that what this tool says can be
    tested as a value — the summary counts are the part a curator acts on, and
    prose that ships to a caller is behaviour like any other.
    """
    lines = [
        f"Read {report.records_read} record(s) from the index against {art_root}.",
        f"  {len(report.created)} work(s) created, {len(report.already_present)} already present,"
        f" {report.records_collapsed} record(s) collapsed into a work already described.",
    ]
    if not report.noted:
        lines.append("  Every work seeded cleanly.")
        return lines
    lines.append(f"  {len(report.noted)} work(s) need attention:")
    for work in report.noted:
        lines.append(f"    {work.title}")
        lines.extend(f"      - {entry.detail}" for entry in work.notes)
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
