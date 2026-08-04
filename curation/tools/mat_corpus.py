"""Run the mat engine over the 41-work corpus and build the sheet an operator judges.

**This is the product's subjective quality bar, and it cannot be automated.**
`nonfunctional-requirements.md` says mat colour must be at least as good as the
2024 implementation, that the bar is explicitly subjective, and that an engine
scoring well on any metric while producing visibly worse mats on these 41 has
failed. So this tool does not pass or fail anything. It renders each work twice —
in the colour 2024 chose and in the colour the engine chooses now — side by side,
and puts the pair in front of a person.

The ΔE column is reported for orientation, not as a score. A large distance means
"a different colour", which is what a different model choosing a mat should
produce; ranking on it would be fitting a subjective judgement to one prior
sample of it.

Usage:

    cd curation
    uv run python tools/mat_corpus.py ../all.json --out /tmp/mat-corpus

    # ...and without spending anything, to see what the mechanical producer does:
    uv run python tools/mat_corpus.py ../all.json --out /tmp/mat-corpus --no-model

**It spends money** — one vision call per work, about $0.0026 for all 41 at the
shipped model's measured rate — and needs `OPENROUTER_API_KEY` and the network.
Images come from each work's museum as a small IIIF derivative rather than from
`ART_ROOT`, so it runs on a machine that has never acquired anything.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from curation.acquisition.color import hex_distance, parse_hex  # noqa: E402
from curation.acquisition.mat import MatEngine  # noqa: E402
from curation.config import DEFAULT_MAT_IMAGE_MAX_EDGE, DEFAULT_MAT_MAX_OUTPUT_TOKENS, DEFAULT_MAT_MODEL  # noqa: E402
from curation.discovery.openrouter import OpenRouterClient  # noqa: E402
from curation.seed.legacy import read_index  # noqa: E402

#: ARTIC's own standard derivative width, so the IIIF server normally serves one
#: it has already generated rather than rendering one on demand.
IIIF_WIDTH = 843

#: How wide each work is drawn on the contact sheet, and how tall its mat swatch
#: bands are. Large enough that a mat's relationship to the picture is visible,
#: small enough that 41 rows fit in a file a browser will open.
TILE = 420
BAND = 54


def _fetch(client: httpx.Client, url: str) -> bytes | None:
    """The work's image from its museum, or None with a reason printed.

    Only ARTIC URLs resolve: the corpus is entirely ARTIC works, and inventing a
    second provider's URL scheme here would be code with no input to exercise it.
    """
    match = re.search(r"artworks/(\d+)", url)
    if not match:
        return None
    try:
        meta = client.get(f"https://api.artic.edu/api/v1/artworks/{match.group(1)}?fields=id,image_id").json()
        image_id = meta["data"]["image_id"]
        return client.get(f"https://www.artic.edu/iiif/2/{image_id}/full/{IIIF_WIDTH},/0/default.jpg").content
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print(f"    could not fetch: {type(exc).__name__}: {exc}")  # noqa: T201 - the report is this tool's output
        return None


def _tile(image: Image.Image, mat_hex: str, caption: str) -> Image.Image:
    """One work inside one mat, captioned — the unit the operator compares."""
    tile = Image.new("RGB", (TILE, TILE + BAND), parse_hex(mat_hex))
    inner = image.copy()
    inner.thumbnail((TILE - 60, TILE - 60), Image.Resampling.LANCZOS)
    tile.paste(inner, ((TILE - inner.width) // 2, (TILE - 60 - inner.height) // 2 + 24))
    draw = ImageDraw.Draw(tile)
    draw.rectangle([0, TILE, TILE, TILE + BAND], fill=(24, 24, 24))
    draw.text((10, TILE + 8), caption, fill=(235, 235, 235))
    draw.text((10, TILE + 28), mat_hex, fill=(160, 160, 160))
    return tile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("index", type=Path, help="the 2024 index, normally all.json at the repository root")
    parser.add_argument("--out", type=Path, required=True, help="where the sheet and the report are written")
    parser.add_argument("--model", default=DEFAULT_MAT_MODEL, help="which vision model to ask")
    parser.add_argument("--limit", type=int, default=0, help="only the first N works, for a cheap look")
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="skip the vision model and show what the mechanical producer alone does. Spends nothing.",
    )
    arguments = parser.parse_args()

    records = read_index(arguments.index)
    if arguments.limit:
        records = records[: arguments.limit]

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key and not arguments.no_model:
        print("OPENROUTER_API_KEY is not set. Set it, or pass --no-model to see the mechanical producer.")  # noqa: T201
        return 2
    client = (
        None
        if arguments.no_model
        else OpenRouterClient(key, model=arguments.model, max_output_tokens=DEFAULT_MAT_MAX_OUTPUT_TOKENS)
    )
    engine = MatEngine(client, image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE)

    arguments.out.mkdir(parents=True, exist_ok=True)
    images = arguments.out / "sources"
    images.mkdir(exist_ok=True)
    http = httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "samsung-frame-art-loader mat corpus"})

    rows, spent, fallbacks = [], 0, 0
    tiles: list = []
    skipped: list[str] = []
    for index, record in enumerate(records):
        print(f"[{index + 1}/{len(records)}] {record.title[:56]}")  # noqa: T201
        body = _fetch(http, record.url)
        if body is None:
            # Counted and named at the end rather than only printed here. A run
            # that reported "33 works" with no mention of the other eight would
            # read as a complete corpus look, which is exactly the impression a
            # subjective quality gate must not give.
            skipped.append(record.title)
            continue
        path = images / f"{index:02d}.jpg"
        path.write_bytes(body)

        choice = engine.choose(path)
        spent += float(choice.cost_usd)
        fallbacks += choice.method.value == "dominant_color_fallback"
        distance = hex_distance(record.mat_hex, choice.hex_rgb)
        rows.append(
            {
                "title": record.title,
                "url": record.url,
                "corpus_hex": record.mat_hex,
                "engine_hex": choice.hex_rgb,
                "method": choice.method.value,
                "delta_e": round(distance, 1),
                "reason": choice.reason,
                "fallback_detail": choice.fallback_detail,
                "cost_usd": str(choice.cost_usd),
            }
        )
        print(f"    2024 {record.mat_hex}   now {choice.hex_rgb}  dE {distance:5.1f}  {choice.method.value}")  # noqa: T201

        with Image.open(path) as source:
            work = source.convert("RGB")
            tiles.append(
                (
                    _tile(work, record.mat_hex, f"2024  {record.title[:40]}"),
                    _tile(work, choice.hex_rgb, f"now   dE {distance:.1f}  {choice.method.value}"),
                )
            )

    if tiles:
        sheet = Image.new("RGB", (TILE * 2 + 24, (TILE + BAND + 16) * len(tiles)), (16, 16, 16))
        for row, (left, right) in enumerate(tiles):
            top = row * (TILE + BAND + 16)
            sheet.paste(left, (0, top))
            sheet.paste(right, (TILE + 24, top))
        sheet_path = arguments.out / "corpus.jpg"
        sheet.save(sheet_path, format="JPEG", quality=88, optimize=True)
        print(f"\nsheet: {sheet_path}")  # noqa: T201

    (arguments.out / "report.json").write_text(json.dumps({"compared": rows, "skipped": skipped}, indent=2))
    distances = sorted(row["delta_e"] for row in rows)
    print(  # noqa: T201
        f"\n{len(rows)} of {len(records)} works compared | mechanical fallbacks {fallbacks} | spent ${spent:.4f}\n"
        f"dE to the 2024 colour: min {distances[0] if distances else 0} "
        f"median {distances[len(distances) // 2] if distances else 0} max {distances[-1] if distances else 0}"
    )
    if skipped:
        # Named individually, not just counted: which works are missing decides
        # whether the sheet still covers the range of the corpus or has quietly
        # lost every work of one kind.
        print(f"\n{len(skipped)} works could not be fetched and are NOT on the sheet:")  # noqa: T201
        for title in skipped:
            print(f"  - {title}")  # noqa: T201
        print("  (only artic.edu works resolve; the rest of the corpus is held elsewhere.)")  # noqa: T201
    print(  # noqa: T201
        "\nThe numbers orient; they do not decide. Open the sheet and compare each pair —\n"
        "the requirement is 'at least as good as 2024', judged by eye."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
