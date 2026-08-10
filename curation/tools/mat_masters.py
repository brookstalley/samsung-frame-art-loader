"""Run the mechanical mat derivation over the operator's own masters, paired with 2024's answer.

**This is the half of the mat check that CI cannot hold, and the reason it exists
is that its absence hid a real defect.** `nonfunctional-requirements.md` § Output
Quality makes the 41 hand-tuned 2024 mats the regression corpus. Those colours are
in `all.json` and are checked against the bar by `tests/unit/test_mat_corpus.py` —
but the *images they were derived from* are the operator's masters, which are not
in the repository and must not be. So the producer being judged was never run over
the corpus's own inputs, and for months a test asserting six synthetic flat colours
stayed green while the derivation put a near-white mat over a Mondrian.

A flat colour has no cluster competition and no pale regions. Real paintings have
both. That is the whole gap, and this tool is what closes it — by hand, on the one
machine that holds the masters.

**It reads and reports; it writes nothing.** No catalogue row, no rendition, no
file under `ART_ROOT`. Run it after any change to `acquisition/mat.py` or
`acquisition/color.py`:

    cd curation
    uv run python tools/mat_masters.py ../all.json

Works are paired to the corpus **by title**, which is what the two records share —
`all.json` predates the catalogue's identifiers, so there is no id to join on. A
work whose title does not match is skipped and counted, rather than silently
dropped: a run that paired twelve of forty and said nothing would report excellent
numbers about almost nothing.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from statistics import median

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from curation.acquisition.color import format_hex, hex_distance, parse_hex, rgb_to_lab  # noqa: E402
from curation.acquisition.mat import CORPUS_MAX_LIGHTNESS, MatChoice, MatEngine, dominant_color  # noqa: E402
from curation.config import CATALOGUE_FILENAME, DEFAULT_MAT_IMAGE_MAX_EDGE  # noqa: E402
from curation.seed.legacy import read_index  # noqa: E402

#: One work as this tool pairs it: its title, its master on disk, and the colour a
#: human chose for it in 2024.
Pair = tuple[str, Path, str]

#: How far two derived colours may sit apart before a re-encode is said to have
#: moved the answer at all. CIEDE2000 puts a just-noticeable difference near 1; 5
#: is where a person comparing two mats side by side stops having to look twice.
VISIBLE_DIFFERENCE = 5.0

#: **The count worth reading, and the reason both are printed.** The same metric
#: puts "plainly different colours" near 10, and the two numbers move differently:
#: merging perceptually-identical clusters leaves the number of works that shift
#: *at all* roughly where it was, while cutting the ones that shift to a different
#: colour entirely. Reporting only the first would say the merge did nothing;
#: reporting only the second would hide that small drift remains.
PLAINLY_DIFFERENT = 10.0


def _say(line: str) -> None:
    """The report, which is this tool's entire output.

    One place the print rule is waived, rather than one waiver per line: a report
    generator that printed from a dozen sites would collect a dozen suppressions,
    and the next reader would have to check each one for whether it was considered.
    """
    print(line)  # noqa: T201 - this tool's output IS a printed report


def _pairs(art_root: Path, corpus_path: Path) -> tuple[list[Pair], list[str]]:
    """Each master on disk beside the hand-tuned colour for the same painting.

    **The SQL is written out here rather than taken from the repository, and that
    is a decision.** `CatalogueRepository` owns these tables, so this duplicates
    names it could import — but the repository opens the catalogue through the
    plane's configuration, and this tool has to run against an `ART_ROOT` named on
    the command line, including one that is not the configured deployment. The cost
    is real and is stated so nobody has to guess it was considered: a column rename
    passes both suites and breaks this tool, because nothing imports or exercises
    it. `CLAUDE.md` sends an operator here straight after touching the mat engine,
    which is exactly when that would bite.
    """
    # Both paths are checked before either is opened, so a run that is going to
    # fail says which argument is wrong before it does any work.
    catalogue_path = art_root / CATALOGUE_FILENAME
    if not corpus_path.is_file():
        # `read_index` catches a bad *parse* and not a missing file, so without
        # this a mistyped corpus path is a bare traceback rather than the one line
        # that names the fix.
        raise SystemExit(f"No corpus at {corpus_path}. It is the 2024 index, `all.json`, tracked at the repository root.")
    if not catalogue_path.is_file():
        # **`sqlite3.connect` creates the file it cannot find.** On a mistyped
        # `--art-root` that writes an empty database into a directory this tool
        # promises to leave alone, and then dies on "no such table" — leaving the
        # operator a stray file and a message about the wrong problem.
        raise SystemExit(f"No catalogue at {catalogue_path}. Check --art-root or $ART_ROOT; nothing was written.")

    by_title = {record.title.strip().lower(): record.mat_hex for record in read_index(corpus_path)}
    # `as_uri()` rather than an f-string: a path holding `?` or `#` would otherwise
    # be read as URI syntax and open something else, or nothing.
    catalogue = sqlite3.connect(f"{catalogue_path.as_uri()}?mode=ro", uri=True)
    catalogue.row_factory = sqlite3.Row
    try:
        rows = catalogue.execute(
            "SELECT a.title AS title, o.relative_path AS path FROM artworks a JOIN originals o ON o.artwork_id = a.id"
        ).fetchall()
    finally:
        catalogue.close()

    paired, unpaired = [], []
    for row in rows:
        human = by_title.get(row["title"].strip().lower())
        path = art_root / row["path"]
        if human is None or not path.is_file():
            unpaired.append(row["title"])
            continue
        paired.append((row["title"], path, human))
    return paired, unpaired


def _lightness_report(paired: list[Pair], engine: MatEngine) -> None:
    """The comparison that found the defect: derived lightness against the human's."""
    lighter, breaches, gaps, derived = 0, [], [], []
    for title, path, human_hex in paired:
        choice: MatChoice = engine.choose(path)
        machine_l = rgb_to_lab(parse_hex(choice.hex_rgb)).l
        human_l = rgb_to_lab(parse_hex(human_hex)).l
        gaps.append(machine_l - human_l)
        derived.append(machine_l)
        if machine_l > human_l:
            lighter += 1
        if machine_l > CORPUS_MAX_LIGHTNESS:
            breaches.append((title, human_hex, human_l, choice.hex_rgb, machine_l))

    total = len(paired)
    bar = f"{CORPUS_MAX_LIGHTNESS:.0f}"
    _say(f"\n{total} works, each with a hand-tuned mat and a master on disk")
    _say(f"  machine lighter than the human chose ..... {lighter:2d} / {total}   median {median(gaps):+.1f} L*")
    _say(f"  machine over CORPUS_MAX_LIGHTNESS = {bar} ... {len(breaches):2d} / {total}   (human: 0 / {total})")
    _say(f"  median derived lightness ................. {median(derived):.1f} L*")
    for title, human_hex, human_l, machine_hex, machine_l in breaches:
        _say(f"    OVER THE BAR  {title[:40]:40s} human {human_hex} L*{human_l:5.1f}  -> {machine_hex} L*{machine_l:5.1f}")


def _stability_report(paired: list[Pair], scratch: Path) -> None:
    """Whether a benign re-encode moves the answer, which is the other half of #115.

    The re-encode is deliberately gentle — **the same picture at the same
    dimensions, saved again at a different quality** — because the claim under test
    is that nothing about the image changed. Resizing it first would not be that
    claim: `dominant_color` decodes through `draft()`, whose DCT scaling factor
    depends on how large the file is to begin with, so a master downscaled to 1024
    reaches the quantiser as genuinely different pixels. Measured that way the
    derivation looks unstable on works where it is not, and the reported number is
    about resampling rather than about the vote.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    moved = []
    for index, (title, path, _) in enumerate(paired):
        before = dominant_color(path)
        copy = scratch / f"{index}.jpg"
        with Image.open(path) as image:
            image.convert("RGB").save(copy, format="JPEG", quality=92)
        after = dominant_color(copy)
        distance = hex_distance(format_hex(before), format_hex(after))
        if distance > VISIBLE_DIFFERENCE:
            moved.append((title, before, after, distance))

    total = len(paired)
    plainly = [entry for entry in moved if entry[3] > PLAINLY_DIFFERENT]
    _say(f"\n  re-encode moved the derived colour at all  {len(moved):2d} / {total}   (ΔE > {VISIBLE_DIFFERENCE:.0f})")
    _say(f"  ... to a plainly different colour ........ {len(plainly):2d} / {total}   (ΔE > {PLAINLY_DIFFERENT:.0f})")
    for title, before, after, distance in sorted(moved, key=lambda entry: -entry[3]):
        _say(f"    MOVED  {title[:40]:40s} {before} -> {after}   ΔE {distance:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corpus", type=Path, help="Path to all.json, the 2024 index holding the hand-tuned mats.")
    parser.add_argument(
        "--art-root",
        type=Path,
        default=None,
        help="Where the masters and the catalogue live. Defaults to $ART_ROOT.",
    )
    parser.add_argument(
        "--scratch",
        type=Path,
        default=Path("/tmp/mat-masters"),
        help="Where the re-encoded copies are written. Nothing under ART_ROOT is touched.",
    )
    arguments = parser.parse_args()

    art_root = arguments.art_root or (Path(os.environ["ART_ROOT"]) if os.environ.get("ART_ROOT") else None)
    if art_root is None:
        parser.error("ART_ROOT is not set and --art-root was not given; this tool needs the operator's masters.")

    paired, unpaired = _pairs(art_root, arguments.corpus)
    if not paired:
        _say("No work in the catalogue paired with a hand-tuned mat — nothing to measure.")
        return 1

    # No model is asked: this measures the mechanical producer, which is the one
    # every keyless deployment and every model failure lands on.
    engine = MatEngine(None, image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE)
    _lightness_report(paired, engine)
    _stability_report(paired, arguments.scratch)
    if unpaired:
        _say(f"\n  not paired (no hand-tuned mat, or no master on disk) ... {len(unpaired)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
