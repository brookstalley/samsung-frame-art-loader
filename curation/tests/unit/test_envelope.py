"""The result envelope, and the derivation that keeps it honest."""

import json

from curation.mcp.envelope import failure, is_error, ok, to_call_tool_result


def test_a_successful_payload_is_not_an_error():
    assert is_error(ok(artworks=[])) is False


def test_a_failed_payload_is_an_error():
    assert is_error(failure("nope", tool="art_catalogue")) is True


def test_a_payload_with_no_success_field_is_treated_as_an_error():
    # Only a boolean `false` counts as failure, so a malformed payload reports
    # as an error rather than passing as a success nobody checked.
    assert is_error({"artworks": []}) is True


def test_a_non_boolean_success_field_is_treated_as_an_error():
    assert is_error({"success": "true"}) is True


def test_the_wire_result_derives_its_error_flag_from_the_payload():
    assert to_call_tool_result(ok(count=0)).isError is False
    assert to_call_tool_result(failure("nope", tool="art_catalogue")).isError is True


def test_the_payload_goes_out_as_both_text_and_structured_content():
    result = to_call_tool_result(ok(count=2))

    assert result.structuredContent == {"success": True, "count": 2}
    assert json.loads(result.content[0].text) == {"success": True, "count": 2}


def test_every_error_points_at_help():
    payload = failure("Unknown action: 'lst'", tool="art_catalogue")

    assert payload["hint"] == "Use art_catalogue(action='help') to see all actions with their parameters."


def test_an_error_carries_its_enumerated_valid_set_and_an_example():
    payload = failure(
        "Unknown action: 'lst'",
        tool="art_catalogue",
        example="art_catalogue(action='list')",
        enumeration={"valid_actions": ["list", "get", "help"]},
    )

    assert payload["valid_actions"] == ["list", "get", "help"]
    assert payload["example"] == "art_catalogue(action='list')"


def test_success_leads_the_envelope():
    # The flag a reader scans for is the first key, in both directions.
    assert next(iter(ok(count=0))) == "success"
    assert next(iter(failure("nope", tool="art_catalogue"))) == "success"
