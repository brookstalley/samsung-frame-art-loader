"""Render a label to a PNG, or onto the real panel, to see what the sizes produce.

**What this is for, and it changed on 2026-08-11.** The type sizes used to be
three provisional numbers this tool existed to sweep. They are now *derived* from
two physical facts — the panel's diagonal and the distance it is read from —
against one calibrated cap height in arcminutes, so there is nothing here to
sweep by trial any more. What is left for the operator is one judgement,
`--cap-arcmin`, and it is a judgement about human vision rather than about this
wall: how large a letter has to look before it is comfortable to read at a
glance. This renders the whole chain the daemon runs (metadata → layout → Pango)
so that judgement can be checked against real type rather than imagined.

**A PNG is for narrowing, not for settling.** A PNG on a backlit monitor is not
sixteen greys of reflective e-paper read at standing distance, and a rendering
that looks right in one medium does not transfer to the other — the 2026-08-04
type ladder was rendered with PIL/DejaVu and none of its numbers survived contact
with Pango. What a PNG can settle is the layout: what fits, what the drop rule
takes off, whether the hierarchy reads. What only `--panel` can settle is
legibility.

**The report prints arcminutes beside every pixel size**, because a pixel size at
a terminal says nothing about whether the person at the wall can read it. That
gap is not hypothetical: it is what let a body size at half the resolvable cap
height pass a hardware probe, a review and a cutover.

It needs the text stack (`uv sync --group raster`); `--panel` additionally needs
the panel driver (`--group epaper`) and a device to draw on:

    cd display && uv run --group raster python tools/label_preview.py label.png
    cd display && uv run --group raster python tools/label_preview.py label.png --cap-arcmin 11

**`--panel` takes the SPI device, which `display.service` holds while it runs.**
Stop the unit for the pass and start it again afterwards, or the two contend for
the same bus:

    sudo systemctl stop display.service
    cd <checkout>/display && sudo -u <service-user> env HOME=<service-home> \\
        uv run --group raster --group epaper \\
        python tools/label_preview.py --panel --cap-arcmin 11
    sudo systemctl start display.service

The reference deployment's actual paths for that invocation are in
`deploy/README.md` § The cutover, which is where machine-specific values belong —
this file must not name them, per the deployment-values norm.
"""

import argparse
from pathlib import Path

from PIL import Image

from display.panel import Layout, TypeScale, lay_out, margin_for, read_label, type_scale_for
from display.panel.layout import Geometry
from display.panel.pango import PangoRasterizer

#: A work with every field populated, which is the case worth looking at: the
#: label that fits is not interesting, and this is the one the drop rule acts on.
#: Real values from the corpus rather than lorem, because line breaking depends on
#: the actual words and "Artist Name" wraps differently from "Katsushika Hokusai".
#:
#: **The name parts are here, and leaving them out would be the one omission that
#: makes this tool lie.** A label with no parts falls back to the whole name
#: unstyled — correct behaviour, and *not* what a seeded catalogue produces — so a
#: sample missing them would show the operator the fallback while the wall showed
#: the real thing. Hokusai is also the case where the parts matter most: the
#: family name leads in Japanese order, so the wrong split is legible as a
#: mistake rather than merely different.
SAMPLE = {
    "title": "Under the Well of the Great Wave off Kanagawa",
    "artist": "Katsushika Hokusai",
    "artist_family_name": "Katsushika",
    "artist_given_name": "Hokusai",
    "artist_nationality": "Japanese",
    "artist_dates": "1760–1849",
    "date_created": "c. 1830–32",
    "medium": "Colour woodblock print on paper",
    "dimensions": "25.7 × 37.9 cm (10 1/8 × 14 15/16 in.)",
    # Present so the preview shows the panel's last-and-first-dropped line
    # actually being dropped, which is the half of the drop rule that is
    # invisible in the image and only appears in what this tool prints.
    "commentary": "One of thirty-six views, and the one that outran the series.",
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
    parsed.add_argument(
        "--diagonal-inches",
        type=float,
        default=6.0,
        help="the label panel's diagonal; with the distance below it decides every type size",
    )
    parsed.add_argument(
        "--viewing-distance-inches",
        type=float,
        default=84.0,
        help="how far away the panel is read from — 84 is the reference wall's 7 feet",
    )
    parsed.add_argument(
        "--cap-arcmin",
        type=float,
        default=None,
        help="the one judgement left: cap height, in arcminutes, of type comfortable at a glance",
    )
    parsed.add_argument(
        "--margin-px",
        type=int,
        default=None,
        help="override the border, which otherwise derives from the type like the daemon's does",
    )
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

    scale = type_scale_for(
        width_px=args.width_px,
        height_px=args.height_px,
        diagonal_inches=args.diagonal_inches,
        viewing_distance_inches=args.viewing_distance_inches,
    )
    margin = args.margin_px if args.margin_px is not None else margin_for(scale)
    surface = Geometry(width_px=args.width_px, height_px=args.height_px, margin_px=margin)

    if args.panel:
        laid_out = _draw_on_the_panel(args, surface, scale)
    else:
        rasterizer = PangoRasterizer()
        laid_out = lay_out(read_label(SAMPLE).lines(), surface, rasterizer.measure, scale)
        raster = rasterizer.render(laid_out)
        Image.frombytes("L", (raster.width_px, raster.height_px), raster.pixels).save(args.output)
        print(f"wrote {args.output} — {args.width_px}x{args.height_px}, margin {margin}")

    _report(laid_out, scale, args)
    return 0


def _apply_overrides(args: argparse.Namespace) -> None:
    """Patch the calibrated constants this run is trying out.

    **Patched rather than parameterised, because these are module constants the
    daemon reads** and a settled value replaces them there. A tool that took its
    own copy would be a second place they live, and the number the operator
    settled would not be the number the wall runs.

    Only two remain patchable, and that is the shape of the change: the type
    sizes are no longer numbers to try, they are consequences of `--cap-arcmin`
    and the geometry. Sweeping sizes directly would be sweeping past the
    derivation the whole label now rests on.
    """
    from display.panel import layout as layout_module
    from display.panel import legibility as legibility_module

    if args.cap_arcmin:
        legibility_module.COMFORTABLE_CAP_ARCMIN = args.cap_arcmin
    if args.measure_em:
        layout_module.MEASURE_EM = args.measure_em


def _draw_on_the_panel(args: argparse.Namespace, surface: Geometry, scale: TypeScale) -> Layout:
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
        type_scale=scale,
        rotate_degrees=args.rotate_degrees,
    )
    try:
        laid_out = lay_out(read_label(SAMPLE).lines(), panel.geometry, panel.measure, panel.type_scale)
        # Blocks for 1.5-1.9s: there is no partial refresh on this driver, so
        # every candidate is a whole frame.
        panel.show(laid_out)
        print(f"drew on {args.device} — {args.width_px}x{args.height_px}, margin {surface.margin_px}")
        return laid_out
    finally:
        panel.close()


def _report(laid_out: Layout, scale: TypeScale, args: argparse.Namespace) -> None:
    """Say what was placed, what was not, and what angle it all subtends.

    **The arcminutes are the point of this report, not the pixels.** A pixel size
    read off a terminal tells the operator nothing about whether the person at the
    wall can read it — that was exactly the gap that let a body size half the
    resolvable height pass every check this product had.
    """
    from display.panel import layout as layout_module
    from display.panel.legibility import CAP_RATIO, pixels_per_arcminute, pixels_per_inch

    per_arcmin = pixels_per_arcminute(
        ppi=pixels_per_inch(width_px=args.width_px, height_px=args.height_px, diagonal_inches=args.diagonal_inches),
        viewing_distance_inches=args.viewing_distance_inches,
    )
    print(
        f'  {args.diagonal_inches}" panel read from {args.viewing_distance_inches}"'
        f" — {per_arcmin:.2f} px per arcminute, measure {layout_module.MEASURE_EM}em"
    )
    for block in laid_out.blocks:
        arcmin = (block.size_px * CAP_RATIO) / per_arcmin
        print(f"  {block.size_px:>3} px = {arcmin:>5.1f}' cap at y={block.y_px:<5} {block.text}")
    print(f"  tiers: {scale.primary_px} px primary over a {scale.floor_px} px floor")
    if laid_out.dropped:
        # The drop rule is the thing this tool exists to make visible: it is
        # invisible in the image, which is precisely the point of it.
        print(f"  DROPPED (no room at these sizes): {', '.join(laid_out.dropped)}")


if __name__ == "__main__":
    raise SystemExit(main())
