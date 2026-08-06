"""Does the configured panel diagonal match the television that is actually there?

`TV_PANEL_DIAGONAL_INCHES` is the sole denominator of every inch this product
reasons about — `ppi = diagonal_px / diagonal_inches`, and from that comes whether
a work is big enough for the wall. It is optional with a default of 42, and **the
default is a plausible wrong answer rather than an obvious one**: a live
deployment ran `TV_PANEL_DIAGONAL_INCHES=42` against a 50" `QN50LS03DAFXZA` on
2026-08-04. Nothing raised. 104.9 ppi where the truth was 88.1, and every
judgement about whether a work was large enough was silently mis-sized.

`.env.example` and the change log both claimed the set names its own size in
`modelName`, "so this is checkable rather than merely documentable" — and the
change log then admitted that sentence advertised a capability nothing delivered.
This is the check.

**Where it lives, and why here rather than beside the value.** Curation owns the
diagonal and derives every inch from it, and has no client for the television —
no `samsungtvws` dependency, and it never talks to the set. The 2024 plane talks
to the set and owns none of the geometry. Neither side holds both halves, so the
comparison goes where the `modelName` already arrives, and the *decision* goes
here: a module with no heavy imports, which the root suite can import and drive.
That is the same split `tv_delete.forgettable_ids` was extracted for — inline in
`tvart.py` a rule is unreachable by any test, because the root suite cannot import
a module that pulls in PIL and `samsungtvws`.

**It warns; it does not refuse.** A refusal would couple startup to a reachable
television, and the set is not always reachable. The operator's call, recorded
2026-08-06.

**The parse is deliberately narrow, and declines rather than guesses.** It is
verified against one real model string, because the operator's standing
preference is not to write TV-generation handling that cannot be tested against
the single available set. An unrecognised `modelName` produces silence, not a
warning: a check that cried wolf about model lines nobody here can verify would
be turned off, and then the case it was written for goes unreported too.
"""

import re
from typing import Final

#: Samsung's screen-size field, as it appears in `modelName`. The real string
#: this was verified against is `QN50LS03DAFXZA`: a two-letter panel family
#: (`QN`), the diagonal in inches (`50`), the model line (`LS03DA`, which is what
#: makes it a Frame), then a region code.
#:
#: **The `LS` is required, and it is what makes this parse safe rather than
#: clever.** Matching only "two letters then two digits" reads `LS03DAFXZA` as a
#: three-inch panel — a warning so obviously wrong that an operator learns to
#: dismiss the check, taking the eight-inch case with it. Written that way first;
#: caught by the test that says so. Requiring the Frame designation after the
#: size means the pattern matches the thing this product is for and declines
#: everything else, which is the honest ceiling: the operator's standing
#: preference is not to write TV-generation handling that cannot be tested
#: against the single available set.
_MODEL_SIZE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{2}(\d{2})LS\d{2}")

#: How far apart the two may be before it is worth saying anything. Not zero: a
#: deployment may legitimately record 54.6 for a set Samsung markets as 55", and
#: nagging about rounding is how a check gets ignored. One inch is well inside
#: the gap that matters — the fault this exists for was eight.
TOLERANCE_INCHES: Final[float] = 1.0


def size_from_model(model_name: str | None) -> int | None:
    """The diagonal in inches a `modelName` states, or None if it does not state one.

    None for anything unrecognised, which includes a set that reports nothing.
    The caller says nothing in that case: silence about a model line this
    codebase has never seen is the honest answer, and it is what keeps the
    warning below worth reading.
    """
    if not model_name:
        return None
    found = _MODEL_SIZE.match(model_name.strip().upper())
    return int(found.group(1)) if found else None


def not_compared(model_name: str | None, configured_inches: float | None) -> str | None:
    """Why no comparison happened, or None when one did.

    `disagreement` is quiet in three unrelated states — the set named no size
    this parse recognises, the deployment configured none, or the two agree —
    and a caller that reports all three the same way says "checked" about a
    check that measured nothing. That is the failure this pairing exists to
    stop, and it is not hypothetical: a live run reported the panel size
    satisfied while the model name it compared was `None` on every call,
    because the caller was reading it from a payload that has never carried
    one. Nothing in the report distinguished that from a set whose size agreed.

    So the two questions are asked separately. This one says whether the
    comparison was possible; `disagreement` says how it came out. A caller that
    reports a pass without asking this one is claiming a measurement it did not
    take.
    """
    reasons: list[str] = []
    if not model_name:
        # Not "the television reported none": the caller may never have got an
        # answer to ask about. What is certain from here is that no name arrived.
        reasons.append("no model name was read from this television")
    elif size_from_model(model_name) is None:
        reasons.append(f"{model_name} is not a model line this parse has been verified against")
    if configured_inches is None:
        reasons.append(
            "TV_PANEL_DIAGONAL_INCHES is not set, so curation reasons at its built-in default "
            "and nothing here has checked that against this set"
        )
    if not reasons:
        return None
    return "not compared — " + "; ".join(reasons)


def disagreement(model_name: str | None, configured_inches: float | None) -> str | None:
    """What to tell the operator, or None when there is nothing worth saying.

    Three ways to be quiet, and each is a real state rather than a fallthrough:
    the set did not report a size this code recognises, the deployment has not
    configured one, or the two agree. `not_compared` above separates the first
    two from the third, because a caller cannot tell them apart from here and
    reporting a pass for either is a claim to have measured something.
    """
    reported = size_from_model(model_name)
    if reported is None or configured_inches is None:
        return None
    if abs(reported - configured_inches) <= TOLERANCE_INCHES:
        return None
    return (
        f'TV_PANEL_DIAGONAL_INCHES is {configured_inches:g}" but this television reports '
        f'{model_name}, which names a {reported}" panel. Every inch this product reasons about '
        "comes from that number — whether a work is big enough for the wall is judged at "
        f"{_ppi(configured_inches):.1f} pixels per inch instead of {_ppi(float(reported)):.1f} — so "
        "fix it in .env unless the model name is wrong about the set."
    )


#: The panel's own pixel diagonal, for the two figures the warning quotes. A 4K
#: panel is 3840x2160 whatever its physical size, so this is a property of the
#: resolution rather than a deployment value, and quoting the *consequence* is
#: what turns "these two numbers differ" into something worth acting on.
_PANEL_DIAGONAL_PX: Final[float] = (3840**2 + 2160**2) ** 0.5


def _ppi(diagonal_inches: float) -> float:
    return _PANEL_DIAGONAL_PX / diagonal_inches
