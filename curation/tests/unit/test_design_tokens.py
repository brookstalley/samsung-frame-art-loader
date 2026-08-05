"""The accessibility baseline, asserted against the stylesheet rather than claimed.

WCAG 2.1 AA is a recorded decision for this surface, and "AA contrast verified"
is exactly the kind of sentence that is true on the day it is written and false
three token edits later. So the check reads the real token values out of
`app.css` and computes the ratios: a colour nudged to look nicer fails the suite
instead of quietly failing a reader.

**Two floors, deliberately, and the difference is not a loophole.** WCAG 1.4.11
governs the parts of a component needed to *identify* it — a control's boundary,
a state indicator — at 3:1. It does not govern a decorative rule between a card
and the page, and holding one to a control's floor would put a hard line around
every picture on a surface whose whole constraint is that chrome recedes behind
the artwork. `--border` is that decorative rule and is unchecked; controls use
`--border-strong`, which is checked.
"""

import re
from pathlib import Path

import pytest

from curation.http.pages import STATIC_DIR
from curation.persistence.discovery_records import ResolutionStatus, WorkProvenance
from curation.persistence.records import ArtworkStatus
from curation.services.display_fit import DisplayFit

#: Normal text. Nothing on this surface is large enough to claim the 3:1 relief
#: AA gives text at 18.66px bold or 24px regular, so every pair is held to 4.5.
TEXT_CONTRAST_FLOOR = 4.5

#: Control boundaries and state indicators, per WCAG 1.4.11.
UI_CONTRAST_FLOOR = 3.0

TEXT_TOKENS = ("text-strong", "text", "text-muted")
SURFACES = ("surface-0", "surface-1", "surface-2")


def _balanced_block(css: str, header: str, *, start: int = 0) -> tuple[str, int, int]:
    """The text inside the balanced braces after `header`, and the span it occupies.

    Brace-counted rather than matched with a regex, and that is not fussiness.
    The first version of this file stripped the token blocks with two non-greedy
    regexes, and the second one **ate three quarters of the stylesheet**: the
    `:root` pattern removed the dark scheme's nested `:root` too, leaving the
    media query with a single closing brace, so the pattern hunting for `}` `}`
    ran on to the end of the file. Every rule after the token blocks then went
    unchecked, and the test suite was entirely green about it.
    """
    at = css.find(header, start)
    assert at != -1, f"app.css has no {header!r} block"
    opening = css.index("{", at)
    depth = 0
    for index in range(opening, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[opening + 1 : index], at, index + 1
    raise AssertionError(f"unbalanced braces after {header!r} in app.css")


def _declared_colours(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block))


def _read_stylesheet() -> tuple[dict[str, dict[str, str]], str]:
    """The token values per colour scheme, and everything that is not a token block.

    The dark scheme is expressed as an override of the light one, which is how it
    is authored and how a browser resolves it — so it is read the same way here
    rather than as a second complete set that would silently pass while missing
    half its tokens.
    """
    css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    light_block, light_from, light_to = _balanced_block(css, ":root")
    dark_media, dark_from, dark_to = _balanced_block(css, "@media (prefers-color-scheme: dark)")
    dark_block, _, _ = _balanced_block(dark_media, ":root")

    light = _declared_colours(light_block)
    schemes = {"light": light, "dark": {**light, **_declared_colours(dark_block)}}
    # Cut the later span first, so removing it cannot shift the earlier one.
    first, second = sorted([(light_from, light_to), (dark_from, dark_to)])
    remainder = css[: first[0]] + css[first[1] : second[0]] + css[second[1] :]
    return schemes, remainder


def _luminance(hex_rgb: str) -> float:
    """Relative luminance, per WCAG 2.1's own definition."""
    value = hex_rgb.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


SCHEMES, COMPONENT_RULES = _read_stylesheet()

TEXT_PAIRS = [(scheme, token, surface) for scheme in SCHEMES for token in TEXT_TOKENS for surface in SURFACES]
UI_PAIRS = [(scheme, "border-strong", surface) for scheme in SCHEMES for surface in SURFACES] + [
    (scheme, "focus", surface) for scheme in SCHEMES for surface in ("surface-0", "surface-1")
]


@pytest.mark.parametrize(("scheme", "token", "surface"), TEXT_PAIRS)
def test_every_text_colour_clears_aa_on_every_surface(scheme, token, surface):
    tokens = SCHEMES[scheme]
    ratio = _ratio(tokens[token], tokens[surface])
    assert ratio >= TEXT_CONTRAST_FLOOR, f"{scheme}: --{token} on --{surface} is {ratio:.2f}:1"


@pytest.mark.parametrize(("scheme", "token", "surface"), UI_PAIRS)
def test_every_control_boundary_clears_the_non_text_floor(scheme, token, surface):
    tokens = SCHEMES[scheme]
    ratio = _ratio(tokens[token], tokens[surface])
    assert ratio >= UI_CONTRAST_FLOOR, f"{scheme}: --{token} on --{surface} is {ratio:.2f}:1"


def test_the_accent_is_legible_both_as_text_and_beneath_its_own_label():
    """The accent is read two ways — as a link, and as a button someone reads text on."""
    for scheme, tokens in SCHEMES.items():
        assert _ratio(tokens["accent"], tokens["surface-1"]) >= TEXT_CONTRAST_FLOOR, scheme
        assert _ratio(tokens["accent-text"], tokens["accent"]) >= TEXT_CONTRAST_FLOOR, scheme


def test_both_schemes_define_every_token_the_light_one_does():
    """A dark scheme missing a token inherits a light one, which is how a dark page grows a white card."""
    light, dark = SCHEMES["light"], SCHEMES["dark"]
    carried = {token for token in light if light[token] == dark[token]}
    assert not carried, f"these colours are not overridden for dark: {sorted(carried)}"


def test_the_client_names_no_colour_outside_the_token_set():
    """A literal colour in a component rule is a colour nobody can check.

    Every value the contrast tests read lives in the two token blocks, so a
    colour written directly into a component rule is invisible to them — which is
    exactly how an unreviewed colour reaches a page whose accessibility is
    "verified". Hex, `rgb()` and `hsl()` all count: the elevation tokens are
    authored as `rgb()` with alpha, so checking only hex would leave the one
    syntax already in use unguarded.
    """
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(", COMPONENT_RULES)
    assert not literals, f"colours written outside the token blocks: {literals}"


def test_the_rules_that_check_was_run_against_are_most_of_the_stylesheet():
    """The check above is only as good as what it was pointed at.

    Its first version cut three quarters of the file away before looking and
    reported clean, which is indistinguishable from a real pass. So the span that
    survives the cut is asserted directly: the token blocks are a small part of
    this stylesheet, and every component rule must still be in what gets scanned.
    """
    css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    assert len(COMPONENT_RULES) > len(css) * 0.5, "the token-block cut removed most of the stylesheet"
    for selector in (".card-image", ".badge", "button.action", "nav.tabs button", ".skip-link", ":focus-visible"):
        assert selector in COMPONENT_RULES, f"{selector} is not in the text the colour check reads"


def test_every_state_a_badge_can_carry_has_a_block_of_its_own():
    """Two states sharing a class paint identically and drift together.

    An archived work and a below-floor work are unrelated judgements — one is
    catalogue status, the other is display fit — so a colour change intended for
    one must not silently reach the other.

    **The list is derived from the enums, not written out here.** A hardcoded
    tuple is complete on the day it is typed and cannot fail in the direction
    this test exists to catch: a state added to the client with no block of its
    own leaves the tuple untouched and the suite green, because the guard's scope
    would be the tuple rather than what the client can emit. Both enums are
    closed by their own docstrings, so growing one is exactly the event that
    should turn this red.
    """
    #: `accepted` is excluded because `statusBadge` returns null for it — the
    #: absence of a badge is how the ordinary case is shown. `unknown` is the
    #: client's own state for a work with no fit verdict and belongs to no enum,
    #: which is why it is the one literal here.
    states = [str(fit) for fit in DisplayFit]
    states += [str(status) for status in ArtworkStatus if status is not ArtworkStatus.ACCEPTED]
    states += ["unknown"]
    #: The run view's two axes, which emit a per-state class the same way.
    #: `resolutionBadge` writes `badge-${resolution_status}` and
    #: `provenanceBadge` writes `badge-offered`. Without these, a sixth
    #: `ResolutionStatus` is forced by `test_client_vocabulary.py` to supply a
    #: glyph and a sentence and gets no signal that a block is owed — and falls
    #: through to base `.badge`, which is `border: 1px solid`, pixel-identical to
    #: `.badge-resolved`. Two states then paint alike with this guard still green.
    states += [str(status) for status in ResolutionStatus]
    #: `proposed` is excluded for the same reason `accepted` is: `provenanceBadge`
    #: renders it with the base class deliberately, so the supplement is the thing
    #: that stands out rather than the ordinary case.
    states += [str(provenance) for provenance in WorkProvenance if provenance is not WorkProvenance.PROPOSED]

    for state in states:
        assert f".badge-{state}" in COMPONENT_RULES, f"the {state} badge has no block of its own"


def test_the_stylesheet_the_test_read_is_the_one_the_server_serves():
    """Guards against this file quietly checking a stylesheet nothing sends.

    The pages module resolves the static directory that FastAPI mounts; reading
    through it rather than through a path spelled out here is what keeps the
    assertion pointed at the served file after someone moves it.
    """
    assert (STATIC_DIR / "app.css").is_file()
    assert STATIC_DIR == Path(__file__).parents[2] / "src" / "curation" / "http" / "static"
