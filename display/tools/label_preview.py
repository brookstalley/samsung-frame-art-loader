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

**It will not guess the panel's diagonal or its reading distance.** Both come
from this deployment's `.env` — the same two settings the daemon reads, by the
same road — and a flag overrides either. On the machine that owns the panel the
short form below is therefore both convenient and correct; on a machine that owns
no panel it refuses and names the two variables, rather than answering for
somebody else's wall.

**It draws the wall's own records, and `--record` chooses which.** The judgements
left here are comparative rather than absolute: whether the name ladder takes its
second rung too eagerly is answered by putting `wright` and `okeeffe` on the panel
in the same sitting, and whether the withheld identification tier reads as a bug
is answered by `nationality-only`. An instrument locked to one record can render
a label but cannot ask either question. `--record` with no argument draws the
reference record the artifacts' measurements were taken against.

It needs the text stack (`uv sync --group raster`); `--panel` additionally needs
the panel driver (`--group epaper`) and a device to draw on:

    cd display && uv run --group raster python tools/label_preview.py label.png
    cd display && uv run --group raster python tools/label_preview.py label.png --cap-arcmin 11
    cd display && uv run --group raster python tools/label_preview.py short.png --record okeeffe

    # away from the deployment, or trying a different wall on for size:
    cd display && uv run --group raster python tools/label_preview.py label.png \\
        --diagonal-inches 10.3 --viewing-distance-inches 120

**`--panel` takes the SPI device, which `display.service` holds while it runs.**
Stop the unit for the pass and start it again afterwards, or the two contend for
the same bus:

    sudo systemctl stop display.service
    cd <checkout>/display && sudo -u <service-user> env HOME=<service-home> \\
        uv run --group raster --group epaper \\
        python tools/label_preview.py --panel --cap-arcmin 11 --record hokusai
    sudo systemctl start display.service

Stop the unit once and draw each record you want to compare, rather than stopping
and starting it around every one: the panel holds the last frame it was given, so
the sitting is a sequence of `--record` runs against one stopped service.

The reference deployment's actual paths for that invocation are in
`deploy/README.md` § The cutover, which is where machine-specific values belong —
this file must not name them, per the deployment-values norm.
"""

import argparse
from pathlib import Path

from PIL import Image

from display.panel import Case, Layout, Run, Slant, TypeScale, Weight, lay_out, margin_for, read_label, set_text, type_scale_for
from display.panel.corpus import CORPUS
from display.panel.layout import Geometry
from display.panel.pango import PangoRasterizer

#: The records this tool can draw, by the name `--record` takes.
#:
#: **The corpus itself, rather than a sample of this file's own.** A tool that
#: carried its own specimen drifts from the one the tests measure and the
#: artifacts quote, and it did: the specimen here was a verbatim copy of
#: `HOKUSAI`, so the instrument and the suite agreed only for as long as somebody
#: kept them in step by hand.
#:
#: It also decides what the operator is able to look at, which is the thing that
#: matters more. The label's hardest judgements are comparative — whether the name
#: ladder takes its second rung too eagerly can only be seen by putting a long
#: name and a short one on the panel in the same sitting — and an instrument
#: locked to one record cannot ask that question at all.
RECORDS = dict(CORPUS)

#: What `--record` draws when the operator names none: the reference record every
#: panel measurement in `accessibility-spec.md` was taken against, every optional
#: field populated, and the only one where the drop rule and the name ladder both
#: have to act. The label that fits is not the interesting one.
DEFAULT_RECORD = "hokusai"


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
    parsed.add_argument(
        "--record",
        choices=sorted(RECORDS),
        default=DEFAULT_RECORD,
        help="which of the wall's records to set; the judgements this tool exists for are comparative",
    )
    parsed.add_argument("--rotate-degrees", type=int, default=180)
    parsed.add_argument("--width-px", type=int, default=1448)
    parsed.add_argument("--height-px", type=int, default=1072)
    # **No defaults, and this file names neither number.** They are the two
    # settings the display plane deliberately ships without a fallback, because a
    # guessed viewing distance gives silently illegible type — the one failure the
    # whole derivation exists to prevent, and the one that looks like success from
    # every direction. Defaulting them here would reintroduce it by the back door
    # on the very instrument an operator uses to judge the result: a second wall
    # would be calibrated against the reference wall's geometry, and the report
    # would echo numbers nobody supplied. `.env.example` ships both empty for the
    # same reason. Where they come from instead is `_viewing_conditions` below.
    parsed.add_argument(
        "--diagonal-inches",
        type=float,
        default=None,
        help="the label panel's diagonal; overrides EPD_PANEL_DIAGONAL_INCHES",
    )
    parsed.add_argument(
        "--viewing-distance-inches",
        type=float,
        default=None,
        help="how far away the panel is read from; overrides EPD_VIEWING_DISTANCE_INCHES",
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
    _viewing_conditions(args, parsed)

    scale = type_scale_for(
        width_px=args.width_px,
        height_px=args.height_px,
        diagonal_inches=args.diagonal_inches,
        viewing_distance_inches=args.viewing_distance_inches,
    )
    margin = args.margin_px if args.margin_px is not None else margin_for(scale)
    surface = Geometry(width_px=args.width_px, height_px=args.height_px, margin_px=margin)

    record = RECORDS[args.record]
    if args.panel:
        laid_out = _draw_on_the_panel(args, record, surface, scale)
    else:
        rasterizer = PangoRasterizer()
        laid_out = lay_out(read_label(record).candidates(), surface, rasterizer.measure, scale)
        raster = rasterizer.render(laid_out)
        Image.frombytes("L", (raster.width_px, raster.height_px), raster.pixels).save(args.output)
        print(f"wrote {args.output} — {args.width_px}x{args.height_px}, margin {margin}")

    _report(laid_out, scale, args)
    return 0


def _viewing_conditions(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Fill in the panel's geometry from the deployment, and refuse to guess it.

    **The same two values the daemon reads, by the same road.** A flag wins where
    one is given — trying out a different distance is the point of the tool — and
    anything it does not give comes from this deployment's `.env`, exactly as
    `__main__` takes it. So on the machine that owns the panel the short
    invocation is both convenient and correct, while on a machine that owns no
    panel it says so instead of quietly answering for someone else's wall.

    **Nothing falls back to a number.** This file naming a diagonal or a distance
    would put the reference wall's geometry inside the instrument used to judge a
    *different* wall, and the report would then echo figures nobody supplied —
    which is the failure the derivation exists to prevent, arriving on the one
    surface that is supposed to expose it.

    Refuses through `parser.error`, like the other bad-invocation path above it:
    this is a hand-run tool, and an operator who has not set two environment
    variables needs their two names and the two flags, not a traceback.
    """
    if args.diagonal_inches is not None and args.viewing_distance_inches is not None:
        return

    # Imported here rather than at module scope: reading a deployment's settings
    # is not something this tool should do merely by being imported, and the
    # suite drives `main` without an `.env` in front of it.
    from display.config import load

    try:
        settings = load()
    # prawduct:allow prawduct/broad-except -- every way an .env can be unreadable
    # arrives here, and one printed line plus the refusal below answers all of
    # them; a traceback would bury the two variable names that actually fix it.
    # Not swallowed: the reason is printed, and a run with no other source for
    # the two numbers still refuses rather than continuing.
    except Exception as exc:
        print(f"could not read this deployment's settings: {exc}")  # noqa: T201 -- the report is this tool's output
        settings = None

    if args.diagonal_inches is None and settings is not None:
        args.diagonal_inches = settings.epd_panel_diagonal_inches
    if args.viewing_distance_inches is None and settings is not None:
        args.viewing_distance_inches = settings.epd_viewing_distance_inches

    missing = [
        (name, flag)
        for name, value, flag in (
            ("EPD_PANEL_DIAGONAL_INCHES", args.diagonal_inches, "--diagonal-inches"),
            ("EPD_VIEWING_DISTANCE_INCHES", args.viewing_distance_inches, "--viewing-distance-inches"),
        )
        if value is None
    ]
    if missing:
        parser.error(
            "this panel's viewing conditions are not known, and guessing them is the one thing that must not happen: "
            f"set {' and '.join(name for name, _ in missing)} in this deployment's .env, "
            f"or pass {' and '.join(flag for _, flag in missing)}."
        )


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


def _draw_on_the_panel(args: argparse.Namespace, record: dict[str, str], surface: Geometry, scale: TypeScale) -> Layout:
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
        laid_out = lay_out(read_label(record).candidates(), panel.geometry, panel.measure, panel.type_scale)
        # Blocks for 1.5-1.9s: there is no partial refresh on this driver, so
        # every candidate is a whole frame.
        panel.show(laid_out)
        print(f"drew on {args.device} — {args.width_px}x{args.height_px}, margin {surface.margin_px}")
        return laid_out
    finally:
        panel.close()


def _styling_of(run: Run) -> str:
    """How this run departs from plain type, or nothing when it does not."""
    departures = [
        name
        for name, applies in (
            ("bold", run.weight is Weight.BOLD),
            ("italic", run.slant is Slant.ITALIC),
            ("capitals", run.case is Case.CAPITALS),
        )
        if applies
    ]
    return " ".join(departures)


def _report(laid_out: Layout, scale: TypeScale, args: argparse.Namespace) -> None:
    """Say what was placed, what was not, and what angle it all subtends.

    **The arcminutes are the point of this report, not the pixels.** A pixel size
    read off a terminal tells the operator nothing about whether the person at the
    wall can read it — that was exactly the gap that let a body size half the
    resolvable height pass every check this product had.

    **Each line is printed as the panel sets it, and its styled runs are named
    under it.** A terminal cannot show weight, and the styling is not decorative
    here: the family name's bold capitals are the only thing distinguishing the
    comma that inverts a name from the two that separate a list, so a report that
    printed the recorded text would show the operator a line the panel does not
    draw and hide the one property the collapsed tombstone rests on. Naming the
    runs is also the only look anybody gets at the styling before the panel — a
    PNG on a backlit monitor cannot settle legibility, but it can settle that the
    right words are heavy.
    """
    from display.panel import layout as layout_module
    from display.panel.legibility import CAP_RATIO, pixels_per_arcminute, pixels_per_inch

    per_arcmin = pixels_per_arcminute(
        ppi=pixels_per_inch(width_px=args.width_px, height_px=args.height_px, diagonal_inches=args.diagonal_inches),
        viewing_distance_inches=args.viewing_distance_inches,
    )
    # **Named first, and named on every run.** The judgements this instrument
    # serves are comparative — a long name against a short one, a full record
    # against a nearly empty one — so the operator is reading several of these
    # reports side by side, and one that did not say which record it described
    # would be evidence about nothing in particular.
    print(f"  record: {args.record}")
    print(
        f'  {args.diagonal_inches}" panel read from {args.viewing_distance_inches}"'
        f" — {per_arcmin:.2f} px per arcminute, measure {layout_module.MEASURE_EM}em"
    )
    for block in laid_out.blocks:
        arcmin = (block.size_px * CAP_RATIO) / per_arcmin
        print(f"  {block.size_px:>3} px = {arcmin:>5.1f}' cap at y={block.y_px:<5} {set_text(block.runs)}")
        for run in block.runs:
            how = _styling_of(run)
            if how:
                print(f"        {how}: {run.text!r}")
    print(f"  tiers: {scale.primary_px} px primary over a {scale.floor_px} px floor")
    if laid_out.dropped:
        # The drop rule is the thing this tool exists to make visible: it is
        # invisible in the image, which is precisely the point of it.
        print(f"  DROPPED (no room at these sizes): {', '.join(laid_out.dropped)}")
    if laid_out.shrunk:
        # **Harder to see in the image than a drop, and worse.** A missing
        # dimension is an absence anybody notices; type set below the floor looks
        # like a label until somebody tries to read it from the viewing position.
        print(f"  SHRUNK BELOW THE {scale.floor_px} px FLOOR: {', '.join(laid_out.shrunk)}")


if __name__ == "__main__":
    raise SystemExit(main())
