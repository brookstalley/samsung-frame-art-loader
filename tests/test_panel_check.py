"""The check that a configured panel diagonal matches the television that is there.

`TV_PANEL_DIAGONAL_INCHES` is the sole denominator of every inch this product
reasons about, it is optional with a default of 42, and the default is a
plausible wrong answer rather than an obvious one. A live deployment ran it
against a 50" `QN50LS03DAFXZA` on 2026-08-04: 104.9 pixels per inch where the
truth was 88.1, and every judgement about whether a work was big enough for the
wall was silently mis-sized. `.env.example` and the change log both said the set
names its own size "so this is checkable rather than merely documentable"; the
change log then admitted no check existed.

The decision lives in `panel_check` rather than inline at the call site for the
same reason `tv_delete.forgettable_ids` was extracted: this suite cannot import
`tv_api_check`, which pulls in `samsungtvws`, so a rule written inside it is
unreachable by any test.

**Silence is a behaviour here, not a gap**, so it is asserted as hard as the
warning is. A check that guessed at model lines nobody can verify against a real
set would be turned off, and then the case it was written for goes unreported too.
"""

import pytest

from panel_check import TOLERANCE_INCHES, disagreement, not_compared, size_from_model

#: The set this product is deployed against, and the string its API actually
#: returned on 2026-08-04. The one model line the parse is verified against.
REAL_MODEL = "QN50LS03DAFXZA"


def test_the_real_model_string_is_read_correctly():
    """The measurement that produced this module, kept as its anchor case."""
    assert size_from_model(REAL_MODEL) == 50


def test_the_deployment_fault_that_produced_this_module_is_reported():
    """42 configured, 50 on the wall — the eight inches nothing noticed."""
    warning = disagreement(REAL_MODEL, 42.0)

    assert warning is not None
    assert "42" in warning and "50" in warning


def test_the_warning_quotes_the_consequence_rather_than_only_the_numbers():
    """ "These two differ" is a fact; "you are judging at the wrong ppi" is a reason.

    The pixels-per-inch pair is what connects a config typo to the thing the
    operator actually cares about — works being called too small for a wall they
    would have filled.
    """
    warning = disagreement(REAL_MODEL, 42.0)

    assert "104.9" in warning, "the ppi actually in use"
    assert "88.1" in warning, "the ppi that would be right"
    assert ".env" in warning, "and where to fix it"


def test_a_diagonal_that_agrees_says_nothing():
    assert disagreement(REAL_MODEL, 50.0) is None


def test_a_rounding_difference_says_nothing():
    """A set marketed as 55" may legitimately be recorded as 54.6.

    Nagging about rounding is how a check gets ignored, and then the eight-inch
    case goes unread with it.
    """
    assert disagreement("QN55LS03DAFXZA", 55 - TOLERANCE_INCHES) is None


def test_a_difference_past_the_tolerance_is_reported():
    """The paired positive: tolerance must not become indifference."""
    assert disagreement("QN55LS03DAFXZA", 55 - TOLERANCE_INCHES - 0.5) is not None


@pytest.mark.parametrize(
    "model",
    [
        None,
        "",
        "not a samsung model string",
        "LS03DAFXZA",
        "QN5",
        "SOMETHING-50-INCH",
    ],
)
def test_a_model_string_this_parse_has_not_been_verified_against_says_nothing(model):
    """Declines rather than guesses, which is the operator's standing preference.

    Writing TV-generation handling that cannot be tested against the single
    available set is how this codebase gets rules nobody can check. An
    unrecognised string is silence — the check reports on what it knows and
    nothing else.
    """
    assert size_from_model(model) is None
    assert disagreement(model, 42.0) is None


def test_a_deployment_that_configured_nothing_says_nothing():
    """No configured value is not a disagreement; it is the default doing its job."""
    assert disagreement(REAL_MODEL, None) is None


def test_the_size_is_read_from_the_start_of_the_string_not_from_anywhere_in_it():
    """Anchored, so it reads the panel size and never some other number further along.

    `QN50LS03DAFXZA` has a `03` in it. An unanchored search for two digits would
    find whichever came first depending on how the pattern was written, and a
    check reporting a 3" panel is worse than no check — it is a warning the
    operator learns to dismiss.
    """
    assert size_from_model(REAL_MODEL) == 50
    assert size_from_model("LS03QN50DAFXZA") is None


def test_a_lowercase_model_string_is_still_read():
    """The field is a string from a foreign API; nothing guarantees its case."""
    assert size_from_model(REAL_MODEL.lower()) == 50


def test_a_comparison_that_can_be_made_reports_no_reason_it_could_not():
    """The paired positive, and the only state in which a caller may report a pass."""
    assert not_compared(REAL_MODEL, 50.0) is None
    assert not_compared(REAL_MODEL, 42.0) is None, "a disagreement is still a comparison"


@pytest.mark.parametrize(
    "model, configured, expected_in_reason",
    [
        (None, 42.0, "reported no model name"),
        ("", 42.0, "reported no model name"),
        ("not a samsung model string", 42.0, "not a samsung model string"),
        (REAL_MODEL, None, "TV_PANEL_DIAGONAL_INCHES is not set"),
    ],
)
def test_every_quiet_state_that_is_not_an_agreement_says_why(model, configured, expected_in_reason):
    """The silent pass this pairing exists to stop, one state at a time.

    Each of these makes `disagreement` return None for a reason that has nothing
    to do with the two sides agreeing. A caller reading only that answer reports
    a satisfied check over a measurement it never took — which is exactly what a
    live run did, for every call, while the model name it was comparing came
    from a payload that has never carried one.
    """
    assert disagreement(model, configured) is None, "the state under test is a quiet one"

    reason = not_compared(model, configured)

    assert reason is not None
    assert expected_in_reason in reason


def test_both_sides_missing_names_both_rather_than_the_first_it_meets():
    """An operator who fixes only the half they were told about runs the check again for nothing."""
    reason = not_compared(None, None)

    assert "reported no model name" in reason
    assert "TV_PANEL_DIAGONAL_INCHES is not set" in reason


def test_an_unset_diagonal_says_the_default_is_in_use_rather_than_that_nothing_is():
    """ "Not configured" is not "no opinion" — curation reasons at its default regardless.

    The fault this module exists for is a diagonal that disagrees with the set,
    and an unset one reaches it by a different road: the default applies, it is a
    plausible wrong answer, and nothing has checked it against this television.
    Saying only "not set" would read as harmless.
    """
    reason = not_compared(REAL_MODEL, None)

    assert "built-in default" in reason
    assert "has checked that against this set" in reason
