"""The tool boundary's last catch: an unexpected fault must not read as success.

`dispatch`'s `except Exception` carries a `prawduct:allow prawduct/broad-except`
waiver, and until 2026-08-05 no test exercised it. That is the combination that
rots — a waiver says "reviewed and intentional", and nothing was checking that
what it waives still does what the review approved.

It matters more here than a coverage gap usually does, because the failure it
prevents is this codebase's own recorded one: the 2024 `upload_file` caught every
exception, recorded a null content id, and returned having set success to true.
A fault reported as a success is worse than a crash, since nothing downstream
looks again.

The sibling branch — an action declared but unbound — is deliberately untested
and says so at its site: `bindings.py` refuses at import to let that state exist,
so reaching the branch would mean defeating the check that makes it impossible.
"""

import json
import logging

import pytest

from curation.mcp.bindings import BINDINGS
from curation.mcp.envelope import to_call_tool_result
from curation.mcp.server import dispatch
from curation.services.errors import ServiceError

#: Details a fault might carry that must not cross the wire. The path is the kind
#: of thing a real `sqlite3.OperationalError` puts in its message, the class name
#: is what a bare `str(exc)` would leak, and the traceback header is what logging
#: the exception adds — three different routes to the same disclosure.
_LEAKED_PATH = "/Users/someone/private/art/catalogue.sqlite"
_FAULT_MESSAGE = f"sqlite3.OperationalError: unable to open database file {_LEAKED_PATH}"


@pytest.fixture
def exploding_catalogue(monkeypatch):
    """A real bound action whose binding raises something nobody anticipated.

    Patched into `BINDINGS` rather than simulated by calling the handler
    directly, so the call goes through `dispatch` itself: action resolution,
    validation and the envelope are all part of what is being asserted, and a
    test that skipped them would be asserting a copy of the boundary rather than
    the boundary.
    """

    def _explodes(_services, _arguments):
        raise RuntimeError(_FAULT_MESSAGE)

    monkeypatch.setitem(BINDINGS, ("art_catalogue", "list"), _explodes)


def _call(services):
    return dispatch(services, "art_catalogue", {"action": "list"})


def test_an_unexpected_fault_is_reported_as_a_failure_not_a_success(exploding_catalogue, services, caplog):
    """The waived catch's whole purpose, and the 2024 defect it exists to refuse."""
    with caplog.at_level(logging.ERROR):
        result = to_call_tool_result(_call(services))

    assert result.isError is True
    assert result.structuredContent["success"] is False


def test_no_internal_detail_reaches_the_caller(exploding_catalogue, services, caplog):
    """A model gets something it can act on; the operator gets the trace.

    Asserted over everything that actually crosses — the JSON text block and the
    structured content both, because they are two copies of the payload and a
    leak in either is a leak.
    """
    with caplog.at_level(logging.ERROR):
        result = to_call_tool_result(_call(services))

    crossed = json.dumps(result.structuredContent, default=str) + "".join(
        block.text for block in result.content if block.type == "text"
    )

    assert _LEAKED_PATH not in crossed, "a filesystem path from the fault reached the caller"
    assert "RuntimeError" not in crossed, "the exception class reached the caller"
    assert "sqlite3" not in crossed, "the fault's own text reached the caller"
    assert "Traceback" not in crossed


def test_the_caller_is_told_where_the_details_are_and_how_to_proceed(exploding_catalogue, services, caplog):
    """Withholding the detail is only right if the message says who has it.

    Otherwise the redaction above turns a leak into a dead end.
    """
    with caplog.at_level(logging.ERROR):
        payload = _call(services)

    assert "art_catalogue" in payload["error"]
    assert "server log" in payload["error"]
    assert payload["hint"]


def test_the_operator_gets_the_traceback_the_caller_does_not(exploding_catalogue, services, caplog):
    """The other half of the trade. Swallowing the fault silently is never allowed.

    `log.exception` rather than `log.error`, so the record carries `exc_info` —
    without it the journal names the action and loses the only thing that says
    what went wrong.
    """
    with caplog.at_level(logging.ERROR):
        _call(services)

    faults = [record for record in caplog.records if "failed unexpectedly" in record.getMessage()]
    assert len(faults) == 1, "an unexpected fault left no journal line"
    assert faults[0].exc_info is not None, "the journal line carries no traceback"
    assert _LEAKED_PATH in caplog.text, "the detail withheld from the caller reached nobody at all"


def test_a_service_error_is_not_swallowed_by_the_broad_catch(services, monkeypatch, caplog):
    """The refusal path stays distinguishable from the fault path.

    A `ServiceError` is the deliberate refusal a caller *can* act on, so its own
    message is reported verbatim. If the broad catch reached it first, every
    usage error would arrive as "failed unexpectedly" and every deliberate
    sentence this surface writes would be replaced by the one that teaches
    nothing — including the acquisition remedies, which exist for exactly this.
    """

    def _refuses(_services, _arguments):
        raise ServiceError("Artwork 'nope' is not in the catalogue.")

    monkeypatch.setitem(BINDINGS, ("art_catalogue", "list"), _refuses)

    with caplog.at_level(logging.ERROR):
        payload = _call(services)

    assert payload["success"] is False
    assert payload["error"] == "Artwork 'nope' is not in the catalogue."
    assert "failed unexpectedly" not in payload["error"]
    assert [record for record in caplog.records if "failed unexpectedly" in record.getMessage()] == []
