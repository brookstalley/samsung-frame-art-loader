"""Render a label to a PNG, or onto the real panel, to settle how it should look.

**What this is for.** The label's type sizes, its margin and its measure are
provisional, and only the operator in front of the real panel can settle them —
but walking to the panel for every candidate is how a legibility pass turns into
an afternoon. This renders the whole chain the daemon runs (metadata → layout →
Pango) so a handful of candidates can be narrowed at a desk, and then puts the
survivors on the panel itself, which is the only thing that can close it.

**A PNG is for narrowing, not for settling.** A PNG on a backlit monitor is not
sixteen greys of reflective e-paper read at standing distance, and the whole
reason these numbers are provisional is that a rendering which looks right in one
medium does not transfer to the other. What a PNG can settle is the layout: what
fits, what the drop rule takes off, whether the hierarchy reads. What only
`--panel` can settle is legibility.

It needs the text stack (`uv sync --group raster`); `--panel` additionally needs
the panel driver (`--group epaper`) and a device to draw on:

    cd display && uv run --group raster python tools/label_preview.py label.png
    cd display && uv run --group raster python tools/label_preview.py label.png --title-px 34

**`--panel` takes the SPI device, which `display.service` holds while it runs.**
Stop the unit for the pass and start it again afterwards, or the two contend for
the same bus:

    sudo systemctl stop display.service
    cd <checkout>/display && sudo -u <service-user> env HOME=<service-home> \\
        uv run --group raster --group epaper \\
        python tools/label_preview.py --panel --title-px 34 --measure-em 26
    sudo systemctl start display.service

The reference deployment's actual paths for that invocation are in
`deploy/README.md` § The cutover, which is where machine-specific values belong —
this file must not name them, per the deployment-values norm.
"""

import argparse
from pathlib import Path

from PIL import Image

from display.panel import Layout, lay_out, read_label
from display.panel.layout import Geometry
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
    parsed.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="where to write the PNG; omitted when --panel is drawing instead",
    )
    parsed.add_argument(
        "--panel",
        action="store_true",
        help="draw onto the real e-paper panel instead of writing a PNG",
    )
    parsed.add_argument(
        "--device",
        default="waveshare_epd.it8951",
        help="omni-epd device name for --panel (omni_epd.mock draws nowhere)",
    )
    parsed.add_argument("--rotate-degrees", type=int, default=180)
    parsed.add_argument("--width-px", type=int, default=1448)
    parsed.add_argument("--height-px", type=int, default=1072)
    parsed.add_argument("--margin-px", type=int, default=40)
    parsed.add_argument(
        "--title-px",
        type=int,
        default=None,
        help="override the title size; artist and body scale with it unless given their own",
    )
    parsed.add_argument("--artist-px", type=int, default=None, help="override the artist size outright")
    parsed.add_argument("--body-px", type=int, default=None, help="override the body size outright")
    parsed.add_argument(
        "--measure-em",
        type=float,
        default=None,
        help="override the line-length bound, in multiples of each line's own type size",
    )
    args = parsed.parse_args(argv)

    if args.output is None and not args.panel:
        parsed.error("give an output path, or --panel to draw on the panel")

    _apply_overrides(args)

    surface = Geometry(width_px=args.width_px, height_px=args.height_px, margin_px=args.margin_px)

    if args.panel:
        laid_out = _draw_on_the_panel(args, surface)
    else:
        rasterizer = PangoRasterizer()
        laid_out = lay_out(read_label(SAMPLE).lines(), surface, rasterizer.measure)
        raster = rasterizer.render(laid_out)
        Image.frombytes("L", (raster.width_px, raster.height_px), raster.pixels).save(args.output)
        print(f"wrote {args.output} — {args.width_px}x{args.height_px}, margin {args.margin_px}")

    _report(laid_out)
    return 0


def _apply_overrides(args: argparse.Namespace) -> None:
    """Patch the layout constants this run is trying out.

    **Patched rather than parameterised, because these are module constants the
    daemon reads** and a settled value replaces them there. A tool that took its
    own sizes would be a second place they live, and the number the operator
    settled would not be the number the wall runs.

    `--title-px` alone scales artist and body with it, which keeps the hierarchy
    while sweeping a range; either can then be pinned outright.
    """
    from display.panel import layout as layout_module

    if args.title_px:
        ratio = args.title_px / layout_module.TITLE_SIZE_PX
        layout_module.ARTIST_SIZE_PX = round(layout_module.ARTIST_SIZE_PX * ratio)
        layout_module.BODY_SIZE_PX = round(layout_module.BODY_SIZE_PX * ratio)
        layout_module.TITLE_SIZE_PX = args.title_px
    if args.artist_px:
        layout_module.ARTIST_SIZE_PX = args.artist_px
    if args.body_px:
        layout_module.BODY_SIZE_PX = args.body_px
    if args.measure_em:
        layout_module.MEASURE_EM = args.measure_em


def _draw_on_the_panel(args: argparse.Namespace, surface: Geometry) -> Layout:
    """Put one candidate on the real panel, through the daemon's own surface.

    **`EpaperSurface` rather than the driver**, so what the operator judges is
    what the wall will run: the greyscale read-back, the rotation and the
    conversion of a silent driver failure into a raised one all apply here
    exactly as they do in the daemon.

    Imported inside the function because the driver installs on a Raspberry Pi
    and nowhere else, and this tool's PNG half must keep working on a machine
    that has no panel.
    """
    from display.panel.epaper import EpaperSurface, open_panel  # noqa: PLC0415 -- see above

    rasterizer = PangoRasterizer()
    panel = EpaperSurface(
        epd=open_panel(args.device),
        rasterizer=rasterizer,
        geometry=surface,
        rotate_degrees=args.rotate_degrees,
    )
    try:
        laid_out = lay_out(read_label(SAMPLE).lines(), panel.geometry, panel.measure)
        # Blocks for 1.5-1.9s: there is no partial refresh on this driver, so
        # every candidate is a whole frame.
        panel.show(laid_out)
        print(f"drew on {args.device} — {args.width_px}x{args.height_px}, margin {args.margin_px}")
        return laid_out
    finally:
        panel.close()


def _report(laid_out: Layout) -> None:
    """Say what was placed and, more importantly, what was not."""
    from display.panel import layout as layout_module

    print(
        f"  sizes {layout_module.TITLE_SIZE_PX}/{layout_module.ARTIST_SIZE_PX}/"
        f"{layout_module.BODY_SIZE_PX} px, measure {layout_module.MEASURE_EM}em"
    )
    for block in laid_out.blocks:
        print(f"  {block.size_px:>3} px at y={block.y_px:<5} {block.text}")
    if laid_out.dropped:
        # The drop rule is the thing this tool exists to make visible: it is
        # invisible in the image, which is precisely the point of it.
        print(f"  DROPPED (no room at these sizes): {', '.join(laid_out.dropped)}")


if __name__ == "__main__":
    raise SystemExit(main())
