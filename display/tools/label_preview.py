"""Render a label to a PNG so it can be looked at without standing at the panel.

**What this is for.** The label's type sizes are provisional and only the operator
in front of the real panel can settle them — but walking to the panel for every
candidate is how a legibility pass turns into an afternoon. This renders the whole
chain the daemon runs (metadata → layout → Pango) into a file, so a handful of
candidates can be narrowed to two or three at a desk and the trip to the panel
settles the last of it.

**It is not a substitute for that trip.** A PNG on a backlit monitor is not
sixteen greys of reflective e-paper read at standing distance, and the whole
reason the sizes are provisional is that a rendering which looks right in one
medium does not transfer to the other. What this can settle is the layout: what
fits, what the drop rule takes off, whether the hierarchy reads.

It needs the text stack (`uv sync --group raster`) and no panel:

    cd display && uv run --group raster python tools/label_preview.py label.png
    cd display && uv run --group raster python tools/label_preview.py label.png --title-px 34
"""

import argparse
from pathlib import Path

from PIL import Image

from display.panel import lay_out, read_label
from display.panel.layout import Surface
from display.panel.pango import PangoRasterizer

#: A work with every field populated, which is the case worth looking at: the
#: label that fits is not interesting, and this is the one the drop rule acts on.
#: Real values from the corpus rather than lorem, because line breaking depends on
#: the actual words and "Artist Name" wraps differently from "Katsushika Hokusai".
SAMPLE = {
    "title": "Under the Well of the Great Wave off Kanagawa",
    "artist": "Katsushika Hokusai",
    "artist_nationality": "Japanese",
    "artist_dates": "1760–1849",
    "date_created": "c. 1830–32",
    "medium": "Colour woodblock print on paper",
    "dimensions": "25.7 × 37.9 cm (10 1/8 × 14 15/16 in.)",
}


def main(argv: list[str] | None = None) -> int:
    parsed = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parsed.add_argument("output", type=Path, help="where to write the PNG")
    parsed.add_argument("--width-px", type=int, default=1448)
    parsed.add_argument("--height-px", type=int, default=1072)
    parsed.add_argument("--margin-px", type=int, default=40)
    parsed.add_argument(
        "--title-px",
        type=int,
        default=None,
        help="override the title size; artist and body scale with it in the same proportion as the defaults",
    )
    args = parsed.parse_args(argv)

    if args.title_px:
        # Patched rather than parameterised, because these are module constants
        # the daemon reads and a settled value replaces them there. A tool that
        # took its own sizes would be a second place they live.
        from display.panel import layout as layout_module

        ratio = args.title_px / layout_module.TITLE_SIZE_PX
        layout_module.ARTIST_SIZE_PX = round(layout_module.ARTIST_SIZE_PX * ratio)
        layout_module.BODY_SIZE_PX = round(layout_module.BODY_SIZE_PX * ratio)
        layout_module.TITLE_SIZE_PX = args.title_px

    rasterizer = PangoRasterizer()
    surface = Surface(width_px=args.width_px, height_px=args.height_px, margin_px=args.margin_px)
    laid_out = lay_out(read_label(SAMPLE).lines(), surface, rasterizer.measure)
    raster = rasterizer.render(laid_out)

    Image.frombytes("L", (raster.width_px, raster.height_px), raster.pixels).save(args.output)

    print(f"wrote {args.output} — {args.width_px}x{args.height_px}, margin {args.margin_px}")
    for block in laid_out.blocks:
        print(f"  {block.size_px:>3} px at y={block.y_px:<5} {block.text}")
    if laid_out.dropped:
        # The drop rule is the thing this tool exists to make visible: it is
        # invisible in the image, which is precisely the point of it.
        print(f"  DROPPED (no room at these sizes): {', '.join(laid_out.dropped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
