"""Choosing the colour of the mat a work is shown against.

Two producers, and **which one produced a colour is recorded, never inferred.**
A vision model looks at the work and reasons about it; when it cannot be reached,
cannot be parsed, or answers with something unusable, the work still gets a mat —
derived mechanically from its own dominant colour, darkened. The 2024 pipeline
did exactly this and said nothing, so a considered choice and a mechanical one
were indistinguishable in the data forever afterwards. `MatColor.method` is the
fix, and every path through this module sets it.

**A failed model call is an ordinary outcome, not an incident.** The chosen model
advertises `response_format` but not `structured_outputs`, so a schema is a
request rather than a contract; probing it produced empty content, content
truncated mid-string, and a hex triplet with no leading `#`. Each of those is a
Tuesday. What this module refuses to do is retry until the model complies, or
quietly paint a colour nobody chose.

**Nothing here writes to the catalogue.** It answers "what colour, and how did we
arrive at it"; the service above records it, which is what keeps the whole engine
exercisable without a database or a network.
"""

import base64
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Final

from PIL import Image, ImageOps

from curation.acquisition.color import ColorError, Lab, delta_e, format_hex, lab_to_rgb, parse_hex, rgb_to_lab, scale_lightness
from curation.discovery.openrouter import Completion, ImageAttachment, OpenRouterClient, OpenRouterError
from curation.persistence.records import MatMethod
from curation.services.imaging import reading

log = logging.getLogger(__name__)

#: What the model is asked. The 2024 prompt is the ancestor of this one and its
#: guidance is carried over deliberately — those instructions produced the 41
#: colours that are this product's regression corpus, so departing from them
#: would be changing the thing being measured at the same time as the thing doing
#: the measuring.
#:
#: One instruction is *new* and corrects a mismatch the old prompt had with the
#: product: 2024 told the model the mat was bars on two sides of a 16:9 canvas,
#: because that is what its compositor produced. This one composes a mat of even
#: width on all four sides, so describing it the old way would have the model
#: reasoning about a picture nobody will see.
MAT_PROMPT: Final[str] = """You are choosing a mat colour for a framed artwork that will hang on a wall-mounted display.

The artwork is centred on the display inside a mat that surrounds it on all four sides, so it reads as the mount of a
framed picture rather than as bars beside a video.

Choose the mat colour. Guidelines:
- Reason in CIE LAB space, which aligns with human perception.
- Consider the artwork's palette, mood, and overall aesthetic; if you recognise the work or artist, consider their style.
- Avoid a colour or lightness that blends into the artwork's edges.
- The display is emissive, so a mat brighter than the artwork glares. When in doubt, go darker.
- Prefer a low-chroma colour drawn from the artwork over a neutral grey, but a grey is right when the work is achromatic.

Answer with the chosen colour and a short reason."""

#: The shape asked for. `lab_*` are requested even though the hex already fixes
#: the colour, because `data-model.md` keeps them "when the model returns them" —
#: they record what the model believed it was choosing, which is the evidence for
#: whether an odd choice was odd reasoning or a slipped conversion.
MAT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "hex_rgb": {"type": "string", "description": "The mat colour as a hex triplet, e.g. '#27285b'."},
        "lab_l": {"type": "number", "description": "CIE LAB lightness of the chosen colour, 0-100."},
        "lab_a": {"type": "number", "description": "CIE LAB a* of the chosen colour."},
        "lab_b": {"type": "number", "description": "CIE LAB b* of the chosen colour."},
        "reason": {"type": "string", "description": "One or two sentences on why this colour suits this artwork."},
    },
    "required": ["hex_rgb", "lab_l", "lab_a", "lab_b", "reason"],
    "additionalProperties": False,
}

#: How much of the dominant colour's lightness the fallback keeps. Carried from
#: the 2024 pipeline, which multiplied the dominant colour's luminance by this
#: and produced the corpus — so it is the one figure here with evidence behind
#: it. Applied to L* rather than to a luminance, which is the same intent
#: expressed in the space the mat is reasoned in.
_FALLBACK_LIGHTNESS: Final[float] = 0.66

#: How many colours the fallback clusters the work into before taking the largest.
#: Five, as in 2024. Enough that a painting's background does not swallow its
#: subject, few enough that the largest cluster is a colour rather than a shade.
_FALLBACK_CLUSTERS: Final[int] = 5

#: **The requirement's bar, and the looser of the two numbers here.** No mat in the
#: hand-tuned corpus exceeds it, it is the round figure `nonfunctional-requirements.md`
#: § Output Quality states, and it is what the suite and `tools/mat_masters.py` both
#: report against. It lives in the product rather than in either of them because two
#: hand-typed copies of one bar drift, and an operator reading a tool's "over
#: CORPUS_MAX_LIGHTNESS" is entitled to the number the tests actually guard.
#:
#: Nothing in this module compares against it — the engine enforces the tighter
#: ceiling below. It is exported because the requirement is the product's, not the
#: test suite's.
CORPUS_MAX_LIGHTNESS: Final[float] = 50.0

#: **What the engine actually enforces: the lightest mat the corpus contains.** A
#: mechanically derived colour is held at or under it, because darkening by
#: `_FALLBACK_LIGHTNESS` alone does not keep one inside the corpus's region — run
#: over the operator's masters, the derivation put a mat above the looser
#: `CORPUS_MAX_LIGHTNESS` on 7 of the 40 works that also carry a hand-tuned colour,
#: where the human breached it on none. A near-white mat over a Mondrian is the
#: single failure that glares on an emissive panel, and two candidate models were
#: rejected during probing for proposing exactly that.
#:
#: **Two ceilings, and the gap between them is deliberate.** 50 is what the
#: requirement says out loud; 45.2 is what the corpus does. Enforcing the looser one
#: would let the derivation sit 4.8 L* above anything a human ever chose while every
#: test stayed green — which is exactly how the defect above survived.
#:
#: **The number is not typed twice.** `test_mat_corpus.py` derives the corpus's
#: lightest mat from `all.json` and fails if it and this constant disagree, so a
#: corpus that gains a lighter mat cannot leave this sitting here as a figure
#: nothing stands behind.
#:
#: **It fixes the breach, not the bias, and saying so is the point.** The same
#: measurement puts the derivation lighter than the human on 31 of 40, at a median
#: gap of +14.2 L*, and clamping does not move that figure at all — it only removes
#: the tail above the bar. Closing the rest is a question about which colour to
#: choose, not about arithmetic on the one already chosen, and it belongs to the
#: vision model rather than to a second multiplier tuned until a statistic looks
#: better.
#:
#: (Issue #115 records +15.2 for the same 40 pairs. It is not a different
#: measurement and neither number is wrong: the sample is even, the two middle gaps
#: are 13.3 and 15.2, and the issue quoted the upper one where
#: `tools/mat_masters.py` takes the mean the median is defined as. The tool's is the
#: figure to quote, because it is the one a reader can reproduce.)
_DERIVED_LIGHTNESS_CEILING: Final[float] = 45.2

#: How close two of the quantiser's colours must be, in CIEDE2000, to be counted as
#: one colour when the largest is chosen. Ten is where that metric's own scale puts
#: "plainly different colours", so merging below it groups shades of one thing and
#: leaves genuinely different ones competing.
#:
#: **Chosen from the metric's meaning rather than from a score, deliberately.**
#: Sweeping 5, 10, 15 and 20 over the operator's 40 masters moves the count of
#: works whose derived colour survives a re-encode around non-monotonically — 3, 5,
#: 3, 3 — while every one of them delivers the same improvement on the number that
#: matters. Forty works cannot separate those, and picking the value that scored
#: best on them would be fitting the threshold to the sample.
#:
#: What it buys, measured: re-encoding a master moved the derived colour to a
#: *plainly different* one on 5 of 40 works before and 2 of 40 after, and the worst
#: single move fell from ΔE 60.7 — a dark red answered as a near-white — to 45.6.
#: What it does not buy, equally measured: the number of works whose colour moves
#: **at all** is unchanged at 5 of 40. The residue is not a split colour losing a
#: vote; it is two genuinely different regions of one painting close enough in area
#: that a re-encode reorders them. No threshold fixes a real tie, and one wide
#: enough to try would merge the picture into a single colour.
_CLUSTER_MERGE_DISTANCE: Final[float] = 10.0

#: How many halvings the gamut search takes to find the most saturated colour that
#: fits under the ceiling. Twenty resolves the chroma scale to about one part in a
#: million — far finer than the 8-bit channels the answer is rounded into, so the
#: bound is the encoding rather than the search.
_GAMUT_SEARCH_STEPS: Final[int] = 20

#: The longest edge the fallback examines. Dominance is a property of the picture,
#: not of its resolution, and quantising a gigapixel master would spend minutes
#: to reach the same answer.
_FALLBACK_MAX_EDGE: Final[int] = 256

#: What the fallback records as its reason, so a reader of the history sees why a
#: colour was arrived at mechanically rather than an empty field.
_FALLBACK_REASON: Final[str] = "Derived from the artwork's dominant colour, darkened; no vision model choice was available."


@dataclass(frozen=True, slots=True)
class MatChoice:
    """A mat colour and the account of how it was arrived at.

    Shaped to be handed straight to `CatalogueService.record_mat_color`, because
    a caller that had to re-map fields is a caller that can map one wrong.
    """

    hex_rgb: str
    method: MatMethod
    reason: str
    lab_l: float | None = None
    lab_a: float | None = None
    lab_b: float | None = None
    model_id: str | None = None
    #: What the model call cost, or zero when no call was made. Reported rather
    #: than accumulated here: this module chooses a colour, and a running total
    #: belongs to whatever authorised the spending.
    cost_usd: Decimal = Decimal(0)
    #: Why the model did not decide, when it did not. `None` on the model path.
    #: Kept out of `reason`, which is the *colour's* rationale and is shown to a
    #: curator — a parse failure is a fact about the call, not about the colour.
    fallback_detail: str | None = None


class MatEngine:
    """Choose mat colours, preferring a vision model and always producing one."""

    def __init__(self, client: OpenRouterClient | None, *, image_max_edge: int) -> None:
        #: `None` is a deployment with no API key, and it is a supported one: the
        #: plane serves its whole catalogue without paying for anything. Works
        #: acquired there get mechanically-derived mats, recorded as such, rather
        #: than no mat at all — which would leave them unrenderable.
        self._client = client
        if image_max_edge <= 0:
            raise ValueError(f"The mat image edge must be positive, got {image_max_edge}.")
        self._image_max_edge = image_max_edge

    @property
    def model_id(self) -> str | None:
        """Which model this engine asks, or `None` when it cannot ask one."""
        return None if self._client is None else self._client.model

    def choose(self, image_path: Path) -> MatChoice:
        """Pick the mat colour for the image at `image_path`.

        Always returns a choice. Every way the model path can fail lands on the
        dominant-colour fallback with the failure recorded on the result, so the
        caller never has to decide what to do about a mat that could not be
        chosen — there is no such state.
        """
        if self._client is None:
            return self._fallback(image_path, detail="no OpenRouter key is configured, so no vision model was asked")
        attachment = reading(image_path, lambda: self._encode(image_path))

        try:
            completion = self._client.complete(prompt=MAT_PROMPT, schema=MAT_SCHEMA, image=attachment)
        except OpenRouterError as exc:
            # Includes the two money refusals. Neither is retried here: 403 means
            # the key is spent and will refuse identically, and 402 means the
            # reservation is too large for the credit left, which asking again
            # does not change. Both leave the work with a recorded mechanical mat
            # rather than with none.
            log.info("the mat model could not be reached for %s: %s", image_path.name, exc)
            return self._fallback(image_path, detail=f"the vision model could not be reached: {exc}")

        choice = _read_choice(completion)
        if choice is not None:
            return choice
        return self._fallback(
            image_path,
            detail=_unusable_detail(completion),
            cost_usd=completion.cost_usd,
        )

    def _encode(self, image_path: Path) -> ImageAttachment:
        """The work as a JPEG small enough to send, upright and in RGB.

        The size is the only dial on what a mat call costs, since the image bills
        inside the prompt tokens. EXIF rotation is applied for the same reason
        `measure()` applies it: a model shown a portrait work lying on its side
        reasons about a different picture than the one the wall will show.
        """
        with Image.open(image_path) as image:
            # Decodes at a reduced DCT scale where the format allows, so a
            # 47-megapixel master never becomes a 47-megapixel bitmap on the way
            # to a 768-pixel thumbnail on the smallest machine in the deployment.
            image.draft("RGB", (self._image_max_edge, self._image_max_edge))
            upright = ImageOps.exif_transpose(image) or image
            frame = upright.convert("RGB")
            frame.thumbnail((self._image_max_edge, self._image_max_edge), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            frame.save(buffer, format="JPEG", quality=85, optimize=True)
        return ImageAttachment(base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"), media_type="image/jpeg")

    def _fallback(self, image_path: Path, *, detail: str, cost_usd: Decimal = Decimal(0)) -> MatChoice:
        rgb = reading(image_path, lambda: dominant_color(image_path))
        scaled = scale_lightness(rgb, _FALLBACK_LIGHTNESS)
        darkened = _under_the_corpus_bar(scaled)
        lab = rgb_to_lab(darkened)
        log.info("mat for %s fell back to the dominant colour: %s", image_path.name, detail)
        if darkened != scaled:
            # **The ceiling firing is the one thing about a derived colour that is
            # otherwise unrecoverable.** `method` records that the colour was
            # derived and not chosen, but not that it was then held back — so a
            # curator asking "why is this mat not the colour of the picture?" has
            # nowhere to look, and neither does the operator judging exactly these
            # works. Logged rather than added to `MatChoice`, because the answer is
            # still the mechanical derivation's; the ceiling is how it was computed,
            # not a third producer beside the model and the fallback.
            log.info(
                "mat for %s was held at the corpus ceiling: derived L* %.1f, capped to L* %.1f",
                image_path.name,
                rgb_to_lab(scaled).l,
                lab.l,
            )
        return MatChoice(
            hex_rgb=format_hex(darkened),
            method=MatMethod.DOMINANT_COLOR_FALLBACK,
            reason=_FALLBACK_REASON,
            lab_l=lab.l,
            lab_a=lab.a,
            lab_b=lab.b,
            # No `model_id`: no model chose this. Recording the configured one
            # would attribute a mechanical colour to a model that never saw the
            # work, which is precisely the confusion `method` exists to end.
            model_id=None,
            cost_usd=cost_usd,
            fallback_detail=detail,
        )


def _under_the_corpus_bar(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """The same colour, no lighter than the lightest mat the corpus contains.

    Lightness only: a* and b* are carried through untouched, so a work whose
    dominant colour is a warm ochre gets a darker ochre rather than a grey. The
    clamp is a ceiling and not a scaling — a colour already under the bar is
    returned exactly as it arrived, which is why applying this to the whole corpus
    of derived colours moves only the ones that were over it.

    Deliberately **not** applied to the vision model's answer. The model is asked
    to reason about the work and its answer is a considered choice; silently
    darkening it would make the recorded colour something no one selected, which is
    the invisible-substitution failure `MatColor.method` exists to end. Whether the
    model's answers need a bar of their own is a separate question with separate
    evidence, and is not settled here.
    """
    lab = rgb_to_lab(rgb)
    if lab.l <= _DERIVED_LIGHTNESS_CEILING:
        return rgb
    at_ceiling = lab_to_rgb(Lab(l=_DERIVED_LIGHTNESS_CEILING, a=lab.a, b=lab.b))
    if rgb_to_lab(at_ceiling).l <= _DERIVED_LIGHTNESS_CEILING:
        return at_ceiling
    return _fitted_to_the_gamut(lab)


def _fitted_to_the_gamut(lab: Lab) -> tuple[int, int, int]:
    """The ceiling colour for a hue sRGB cannot show at the ceiling's lightness.

    **Asking for L\\* 45.2 does not always get it.** `lab_to_rgb` clamps into the
    displayable gamut, and for a saturated hue the nearest displayable colour is
    *lighter* than the one asked for: a pure magenta comes back at L\\* 49.6. That
    still clears the corpus's round-number bar of 50, which is why the arithmetic
    looked right — and it is outside the region the corpus actually occupies, which
    is the requirement. A ceiling a chromatic colour can step over is the same
    unverified claim this whole fix exists to remove.

    **Lightness gives way, not chroma, and the corpus is what decides that.** The
    other way round is available — hold L\\* at the ceiling and desaturate until the
    colour fits — and it is wrong here: it answers a vivid blue work with a pure
    grey, when the prompt that produced the corpus says to prefer a low-chroma
    colour *drawn from the artwork* over a neutral. Going darker is the corpus's own
    instruction for exactly this doubt ("when in doubt, go darker"), it keeps the
    mat the work's colour, and L\\* 6.7 is the corpus's floor, so there is room
    beneath the ceiling to move in.

    The search always has an answer — black is displayable at every hue — so it
    terminates on a real colour rather than on a bound.
    """
    fits, exceeds = 0.0, _DERIVED_LIGHTNESS_CEILING
    for _ in range(_GAMUT_SEARCH_STEPS):
        middle = (fits + exceeds) / 2
        if rgb_to_lab(lab_to_rgb(Lab(l=middle, a=lab.a, b=lab.b))).l <= _DERIVED_LIGHTNESS_CEILING:
            fits = middle
        else:
            exceeds = middle
    return lab_to_rgb(Lab(l=fits, a=lab.a, b=lab.b))


def dominant_color(image_path: Path) -> tuple[int, int, int]:
    """The colour that covers most of the image.

    Median-cut quantisation through Pillow rather than k-means through OpenCV,
    NumPy and scikit-image — which is what 2024 used, and what this plane will not
    install on a memory-capped Pi to answer a question about five colours.

    The two agree on what they are asked for. Both partition the image and return
    the most-populated partition's colour; median cut splits along the widest
    channel where k-means iterates towards cluster centres, so an individual
    answer can differ by a shade.

    **A shade's difference here is not the small thing it reads as**, and this
    docstring said it was until the derivation was measured against real paintings.
    Which partition wins decides the mat outright, so a re-encode that moved the
    split moved a work's colour from a near-black navy to a near-white. Darkening
    the result by a third does not absorb that; it darkens the wrong colour.
    **Shades of one colour are therefore counted once** — see `_most_covered_colour`
    for the failure that forces it.
    """
    with Image.open(image_path) as image:
        image.draft("RGB", (_FALLBACK_MAX_EDGE, _FALLBACK_MAX_EDGE))
        upright = ImageOps.exif_transpose(image) or image
        frame = upright.convert("RGB")
        frame.thumbnail((_FALLBACK_MAX_EDGE, _FALLBACK_MAX_EDGE), Image.Resampling.LANCZOS)
        quantised = frame.quantize(colors=_FALLBACK_CLUSTERS, method=Image.Quantize.MEDIANCUT)
        palette = quantised.getpalette() or []
        # `getcolors` on a palette image returns (count, palette index) pairs.
        # None would mean more distinct values than the limit, which quantising to
        # five cannot produce — but a fallback that raised here would defeat its
        # own purpose, so the guard is a value rather than an exception.
        counts = quantised.getcolors(maxcolors=_FALLBACK_CLUSTERS) or [(1, 0)]
    return _most_covered_colour(
        [(count, (palette[index * 3], palette[index * 3 + 1], palette[index * 3 + 2])) for count, index in counts]
    )


def _most_covered_colour(clusters: list[tuple[int, tuple[int, int, int]]]) -> tuple[int, int, int]:
    """The colour covering most of the image, counting shades of one colour once.

    **Taking the largest cluster straight is what made the derivation unstable.**
    Median cut splits along the widest channel, so one perceptual colour spread
    over a gradient — which is most of what paint does — routinely arrives as two
    clusters, and then loses the vote to a smaller rival that happened not to be
    divided. On the operator's masters this is not a shade's difference: one work's
    dominant colour moved from a near-black navy to a near-white, and another from
    a pale grey to a dark blue, on nothing worse than a benign re-encode. A
    re-encode is enough because it is enough to move where the split falls.

    Grouping is **single-link**: a chain of shades each within the threshold of the
    next is one colour, because that is what a gradient is. Connected components do
    not depend on the order the clusters arrive in, so the answer does not either.

    A group's colour is its **most-populous member, never an average** — averaging
    two real colours can produce a third that is nowhere in the picture, which is
    precisely the invented answer a dominant-colour derivation must not give.
    """
    labs = {rgb: rgb_to_lab(rgb) for _, rgb in clusters}
    remaining = list(clusters)
    groups: list[list[tuple[int, tuple[int, int, int]]]] = []
    while remaining:
        group = [remaining.pop()]
        absorbed = True
        while absorbed:
            absorbed = False
            for candidate in list(remaining):
                if any(delta_e(labs[candidate[1]], labs[member[1]]) < _CLUSTER_MERGE_DISTANCE for member in group):
                    group.append(candidate)
                    remaining.remove(candidate)
                    absorbed = True
        groups.append(group)
    # The colour, not just the count, breaks a tie — two groups covering exactly
    # equal area is reachable on flat synthetic input, and a derivation that
    # answered differently on two runs over one file would be the instability this
    # function exists to remove.
    winner = max(groups, key=lambda group: (sum(count for count, _ in group), max(group)))
    return max(winner)[1]


def _read_choice(completion: Completion) -> MatChoice | None:
    """The model's answer as a choice, or `None` if it did not give a usable one.

    Every failure returns `None` rather than raising, because none of them is
    exceptional: an unenforced schema produces malformed answers as a matter of
    course, and the caller's response to all of them is identical.
    """
    try:
        payload = json.loads(completion.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        hex_rgb = format_hex(parse_hex(str(payload.get("hex_rgb", ""))))
    except ColorError:
        return None
    return MatChoice(
        hex_rgb=hex_rgb,
        method=MatMethod.VISION_MODEL,
        reason=str(payload.get("reason") or "").strip(),
        # The model's own LAB, kept as it sent it rather than recomputed from the
        # hex. They can disagree, and when they do that disagreement is the
        # evidence: a hex that does not match the LAB beside it is a model that
        # converted badly, not a model with unusual taste.
        lab_l=_number(payload.get("lab_l")),
        lab_a=_number(payload.get("lab_a")),
        lab_b=_number(payload.get("lab_b")),
        model_id=completion.model_id,
        cost_usd=completion.cost_usd,
    )


def _unusable_detail(completion: Completion) -> str:
    """Why an answer that arrived could not be used, in terms that name the fix.

    `length` is called out by name because it is the one failure whose cause is
    on this side of the wire: the output reservation did not clear the model's
    reasoning budget, and the call was billed in full for nothing. Reported as
    "the model failed" it would send whoever reads it to change models, which
    fixes nothing.
    """
    if completion.finish_reason == "length":
        return (
            f"the model's answer was cut off at the output reservation "
            f"({completion.output_tokens} tokens); raise MAT_MAX_OUTPUT_TOKENS"
        )
    if not completion.content.strip():
        return f"the model returned an empty answer (finish_reason={completion.finish_reason!r})"
    return f"the model's answer was not a usable colour: {completion.content[:200]!r}"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


__all__ = ["CORPUS_MAX_LIGHTNESS", "MAT_PROMPT", "MAT_SCHEMA", "MatChoice", "MatEngine", "dominant_color"]
