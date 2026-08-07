"""The composition root's two refusals to start.

Both say a *deployment value* is wrong — a missing setting, or a store written by
a newer plane than this one — and both are read by a person who has just run the
command at a terminal. So both owe the same three things: a non-zero exit so
systemd and a shell agree something failed, a sentence on stderr rather than only
a JSON log line, and no traceback, because a stack through `load()` points at this
codebase, which is the one place the problem is not.

Tested through `main` rather than through `_run`, because what is under test is
the handling: which exceptions are caught, what they exit with, and what the
operator is told.
"""

import pytest

from display import __main__ as entry
from display.config import ConfigError
from display.state import StateSchemaTooNew


@pytest.fixture(autouse=True)
def _quiet_logging(monkeypatch):
    """`main` configures logging as its first act; leave the suite's alone."""
    monkeypatch.setattr(entry.logs, "configure", lambda: None)


def _raising(exc: Exception):
    async def _run() -> int:
        raise exc

    return _run


@pytest.mark.parametrize(
    ("exc", "what"),
    [
        pytest.param(
            ConfigError("ART_ROOT is not set. Copy .env.example to .env and fill it in."),
            "ART_ROOT",
            id="a missing deployment value",
        ),
        pytest.param(
            StateSchemaTooNew("display-state.sqlite was written by a display plane at schema 9; this one understands 8."),
            "schema 9",
            id="a store from a newer plane",
        ),
    ],
)
def test_a_deployment_fault_refuses_to_start_and_says_so_at_the_terminal(monkeypatch, capsys, exc: Exception, what: str):
    monkeypatch.setattr(entry, "_run", _raising(exc))

    code = entry.main()

    assert code == 2, "a refusal to start exited zero, so systemd would treat it as a clean stop"
    printed = capsys.readouterr().err
    assert "display plane cannot start" in printed
    assert what in printed, "the operator is told it cannot start but not which value is wrong"


def test_an_unexpected_failure_is_not_swallowed_into_a_tidy_exit(monkeypatch):
    """Only the two deployment faults are handled. Anything else must keep its
    traceback: those two are 'the fix is in `.env`', and a bug wearing the same
    two-line exit would send whoever reads it to the wrong file."""
    monkeypatch.setattr(entry, "_run", _raising(RuntimeError("something nobody anticipated")))

    with pytest.raises(RuntimeError):
        entry.main()
