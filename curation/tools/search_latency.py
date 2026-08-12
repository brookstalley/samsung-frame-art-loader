"""Time the collection's retrieval against the thousands-scale corpus, and settle FTS5.

`nonfunctional-requirements.md` made search mandatory when the catalogue target
moved from hundreds of works to thousands, and left one question open that only a
measurement can close: **does text search need SQLite's FTS5, or does a `LIKE`
scan suffice?** The real collection holds tens of works, where the two are
indistinguishable; `tests/conftest.py`'s `build_large_catalogue` exists so the
question has something to run against.

**It reads and reports; it writes nothing** outside a temporary directory it
makes and leaves behind for the OS. No catalogue row, no file under `ART_ROOT`,
no network, no money.

    cd curation
    uv run python tools/search_latency.py
    uv run python tools/search_latency.py --works 8000 --repeats 100

Two things are timed, and they are separate questions:

1. **The whole `GET /api/works` answer** — the page, its total, and a facet count
   per kind — through `CatalogueService.list_artworks`, which is what a curator
   actually waits for. This is the number `api-contract.md`'s revisit trigger for
   recomputing counts per page is about.
2. **The search clause alone**, as `LIKE` and as an FTS5 `MATCH` over the same
   columns, so the FTS5 question is answered on its own rather than through the
   noise of the counts.

**The recorded result is in `api-contract.md` § `GET /api/works`.** Re-run this
after any change to how the collection is queried, and move the number there if
it moves; a figure in a document with no way to reproduce it is a figure nobody
can challenge.
"""

import argparse
import sqlite3
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

_CURATION = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CURATION / "src"))
# `build_large_catalogue` lives with the fixtures that use it. Imported rather
# than copied: a second corpus builder would drift from the one the suite
# measures against, and then this tool would be timing a different collection
# from the one the tests assert over.
sys.path.insert(0, str(_CURATION / "tests"))

from conftest import _open_seeded_catalogue  # noqa: E402

from curation.persistence.durable import SqliteDurableStore  # noqa: E402
from curation.services.catalogue import CatalogueService  # noqa: E402

#: Terms chosen to span selectivity, which is the whole axis the two strategies
#: differ on: a full scan pays the same for every question, an index pays in
#: proportion to what matches. `_PLACES` values like "Ostend" appear in a
#: fortieth of descriptions; "the" appears in almost every one.
_TERMS: Sequence[tuple[str, str]] = (
    ("selective", "Ostend"),
    ("moderate", "harbour"),
    ("broad", "tradition"),
    ("two words", "blue harbour"),
    ("no match", "zzzznothing"),
)


def _percentiles(samples: Sequence[float]) -> tuple[float, float, float]:
    """Median, 95th and worst, in milliseconds.

    A mean would be the wrong summary here: the first call of a run pays for
    SQLite's page cache being cold, and one such sample moves a mean of fifty
    while leaving the median where it belongs.
    """
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return statistics.median(ordered) * 1000, p95 * 1000, ordered[-1] * 1000


def _time(call: Callable[[], object], *, repeats: int) -> tuple[float, float, float]:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        samples.append(time.perf_counter() - started)
    return _percentiles(samples)


def _say(line: str = "") -> None:
    print(line)  # noqa: T201 - this tool's output IS a printed report


def _heading(title: str) -> None:
    _say(f"\n{title}")
    _say(f"  {'':<34} {'median':>7} {'p95':>7} {'worst':>7}")


def _report(label: str, timings: tuple[float, float, float], detail: str = "") -> None:
    median, p95, worst = timings
    _say(f"  {label:<34} {median:7.2f} {p95:7.2f} {worst:7.2f}   {detail}")


def _build_fts_index(connection: sqlite3.Connection, columns: Sequence[str]) -> None:
    """Build a contentless-external FTS5 index over the artworks' text.

    Built here rather than in the schema because **this is the thing being
    decided**: an index the product does not ship, stood up beside the shipped
    query so the two can be timed against the same rows. Nothing here reaches the
    catalogue file the product opens.
    """
    connection.execute(f"CREATE VIRTUAL TABLE search USING fts5({', '.join(columns)}, tokenize='unicode61')")
    connection.execute(
        f"INSERT INTO search ({', '.join(columns)}) "
        f"SELECT {', '.join(f'COALESCE(a.{column}, \'\')' for column in columns)} FROM artworks a"
    )
    connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--works", type=int, default=4000, help="How many works to seed. Default 4000, the fixture's size.")
    parser.add_argument("--repeats", type=int, default=50, help="How many times to run each query. Default 50.")
    parser.add_argument("--seed", type=int, default=20260812, help="The corpus seed, so a run is comparable to the last.")
    arguments = parser.parse_args()

    scratch = Path(tempfile.mkdtemp(prefix="search-latency-"))
    started = time.perf_counter()
    catalogue_file, service, works = _open_seeded_catalogue(
        scratch / "catalogue.sqlite", size=arguments.works, seed=arguments.seed
    )
    build_seconds = time.perf_counter() - started
    try:
        _measure(service, catalogue_file, works=len(works), repeats=arguments.repeats, build_seconds=build_seconds)
    finally:
        catalogue_file.close()
    return 0


def _measure(
    service: CatalogueService, catalogue_file: SqliteDurableStore, *, works: int, repeats: int, build_seconds: float
) -> None:
    facets = sum(len(service.facets_for(work.artwork.id)) for work in service.list_artworks(limit=100).entries)
    _say(f"\n{works} works seeded in {build_seconds:.2f}s; {facets} facet rows on the first 100 of them.")
    _say(f"Every figure below is milliseconds over {repeats} runs.")

    _heading("The whole answer a curator waits for — page, total, and a count per facet kind:")
    _report("unfiltered, first page", _time(lambda: service.list_artworks(limit=25), repeats=repeats))
    for label, term in _TERMS:
        matched = service.list_artworks(q=term, limit=25).total
        _report(
            f"q={term!r} ({label})",
            _time(lambda term=term: service.list_artworks(q=term, limit=25), repeats=repeats),
            f"{matched} works match",
        )
    _report(
        "one facet chosen",
        _time(lambda: service.list_artworks(facets={"movement": ["Baroque"]}, limit=25), repeats=repeats),
    )
    _report(
        "text and two facets",
        _time(
            lambda: service.list_artworks(q="harbour", facets={"movement": ["Impressionism"], "subject": ["Seascape"]}, limit=25),
            repeats=repeats,
        ),
    )

    # The search clause on its own, against the same rows, so the FTS5 question
    # is not answered through the noise of six facet counts.
    columns = ("title", "description", "commentary", "medium", "date_created")
    # Reached directly, which nothing else in this repository does: the index
    # being compared is one the product deliberately does not ship, so there is
    # no store method that could stand it up. A measurement tool, not a caller.
    connection = catalogue_file._connection  # noqa: SLF001
    _build_fts_index(connection, columns)
    like_clause = " OR ".join(f"a.{column} LIKE ? ESCAPE '\\'" for column in columns)

    _heading("The search clause alone — the same term, the same columns, two strategies:")
    like_statement = f"SELECT COUNT(*) FROM artworks a WHERE {like_clause}"
    for _, term in _TERMS:
        like_values = tuple(f"%{term}%" for _ in columns)
        _report(
            f"LIKE  {term!r}",
            _time(
                lambda values=like_values: connection.execute(like_statement, values).fetchone(),
                repeats=repeats,
            ),
            f"{connection.execute(like_statement, like_values).fetchone()[0]} rows",
        )
        # `term*` and not `term`: FTS5 matches whole tokens, so the closest it
        # comes to a contains-match is a prefix one. That difference is the
        # finding, not a detail of how it was timed — see the tool's own report.
        match = " ".join(f"{word}*" for word in term.split())
        _report(
            f"FTS5  {match!r}",
            _time(
                lambda match=match: connection.execute("SELECT COUNT(*) FROM search WHERE search MATCH ?", (match,)).fetchone(),
                repeats=repeats,
            ),
            f"{connection.execute('SELECT COUNT(*) FROM search WHERE search MATCH ?', (match,)).fetchone()[0]} rows",
        )

    _say(
        "\nRead the second table with the row counts beside it: FTS5 matches whole tokens,\n"
        "so 'harb' finds nothing there and 'harbour' inside 'harbourside' is a prefix query\n"
        "away. The two columns are not the same search, which is half of the answer."
    )


if __name__ == "__main__":
    raise SystemExit(main())
