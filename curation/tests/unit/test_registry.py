"""Generation from the registry, and the errors it produces.

These are the tests that make "the schema, the validation, help, and the error
messages all come from one record" a fact rather than an intention.
"""

import pytest

from curation.mcp import registry
from curation.mcp.bindings import BINDINGS
from curation.mcp.registry import HELP_ACTION, Action, ArgumentError, Param, RegistryError, ToolRecord
from curation.mcp.tools import ART_CATALOGUE, ART_REVIEW, TOOLS


def _tool(**overrides) -> ToolRecord:
    defaults = {
        "name": "art_test",
        "title": "Test",
        "summary": "A tool that exists only in this test.",
        "read_only": True,
        "destructive": False,
        "open_world": False,
    }
    return ToolRecord(**{**defaults, **overrides})


# -- generation ---------------------------------------------------------------


def test_every_tool_answers_help_without_declaring_it():
    # Generated rather than declared, so help cannot drift from the schema it
    # documents.
    assert "help" in _tool().action_names


def test_the_schema_flattens_every_actions_parameters_onto_one_object():
    schema = registry.input_schema(ART_CATALOGUE)

    assert schema["required"] == ["action"]
    properties = schema["properties"]
    # `status` comes from `list`, `artwork_id` from `get`; both sit on the one
    # schema, and only `action` is required of the caller by the wire.
    assert {"action", "status", "limit", "offset", "artwork_id"} <= set(properties)


def test_the_schema_carries_each_parameters_valid_set():
    properties = registry.input_schema(ART_CATALOGUE)["properties"]

    assert properties["status"]["enum"] == ["accepted", "archived"]
    assert properties["limit"]["minimum"] == 1
    assert properties["action"]["enum"] == list(ART_CATALOGUE.action_names)


def test_the_description_lists_every_action():
    description = registry.description(ART_CATALOGUE)

    for action in ART_CATALOGUE.action_names:
        assert action in description


def test_an_unbuilt_tool_says_so_in_its_description():
    assert "Not available yet" in registry.description(ART_REVIEW)


def test_help_reports_required_and_optional_parameters_separately():
    payload = registry.help_payload(ART_CATALOGUE)
    get = next(action for action in payload["actions"] if action["action"] == "get")

    assert [param["name"] for param in get["required_parameters"]] == ["artwork_id"]
    assert get["optional_parameters"] == []
    assert get["example"].startswith("art_catalogue(action='get'")


def test_help_reports_a_parameters_valid_values():
    payload = registry.help_payload(ART_CATALOGUE)
    listing = next(action for action in payload["actions"] if action["action"] == "list")
    status = next(param for param in listing["optional_parameters"] if param["name"] == "status")

    assert status["valid_values"] == ["accepted", "archived"]


# -- registry defects are caught at import, not at runtime --------------------


def test_a_tool_declaring_one_parameter_two_ways_is_refused():
    contradictory = (
        Action(name="a", description="", example="", params=(Param(name="n", type="integer", description=""),)),
        Action(name="b", description="", example="", params=(Param(name="n", type="string", description=""),)),
    )

    with pytest.raises(RegistryError, match="inconsistently"):
        _tool(actions=contradictory)


def test_a_tool_declaring_one_parameters_bounds_two_ways_is_refused():
    # The flattened wire schema publishes the first declaration it sees, so
    # divergent bounds would ship one action's ceiling as if it governed both
    # while per-action validation quietly enforced the other.
    contradictory = (
        Action(name="a", description="", example="", params=(Param(name="n", type="integer", description="", maximum=100),)),
        Action(name="b", description="", example="", params=(Param(name="n", type="integer", description="", maximum=500),)),
    )

    with pytest.raises(RegistryError, match="inconsistently"):
        _tool(actions=contradictory)


def test_a_tool_that_declares_actions_while_marked_unavailable_is_refused():
    # The half-finished state of flipping a tool from unbuilt to built: every
    # declared action would answer "not available yet" and no test would fail.
    with pytest.raises(RegistryError, match="still marked unavailable"):
        _tool(
            actions=(Action(name="a", description="", example=""),),
            unavailable_note="Not available yet.",
        )


def test_every_declared_action_is_bound_and_every_binding_is_declared():
    # Availability is otherwise reconstructed from three unreconciled signals.
    # An unbound action reaches a branch the code itself calls a defect; a
    # binding with no action is dead code that reads as a working feature.
    declared = {(tool.name, name) for tool in TOOLS for name in tool.action_names if name != HELP_ACTION}

    assert declared == set(BINDINGS)


def test_a_tool_declaring_the_same_action_twice_is_refused():
    duplicated = (
        Action(name="a", description="", example=""),
        Action(name="a", description="", example=""),
    )

    with pytest.raises(RegistryError, match="twice"):
        _tool(actions=duplicated)


def test_a_parameter_of_an_unsupported_type_is_refused():
    with pytest.raises(RegistryError, match="unsupported type"):
        Param(name="n", type="float", description="")


# -- validation ---------------------------------------------------------------


def test_a_missing_action_is_reported_with_the_valid_set():
    with pytest.raises(ArgumentError) as caught:
        registry.resolve_action(ART_CATALOGUE, {})

    assert caught.value.enumeration["valid_actions"] == list(ART_CATALOGUE.action_names)


def test_an_unknown_action_quotes_it_back_without_guessing_a_correction():
    with pytest.raises(ArgumentError) as caught:
        registry.resolve_action(ART_CATALOGUE, {"action": "lst"})

    assert caught.value.message == "Unknown action: 'lst'"
    # No nearest-match suggestion anywhere: the whole valid set is more useful
    # to a model than one guess, and cannot mislead.
    assert "did you mean" not in caught.value.message.lower()


def test_an_unbuilt_tool_refuses_every_action_but_help():
    with pytest.raises(ArgumentError, match="not available yet"):
        registry.resolve_action(ART_REVIEW, {"action": "set_verdict"})

    assert registry.resolve_action(ART_REVIEW, {"action": "help"}).name == "help"


def test_a_missing_required_parameter_is_named():
    action = ART_CATALOGUE.action("get")

    with pytest.raises(ArgumentError) as caught:
        registry.validate(ART_CATALOGUE, action, {"action": "get"})

    assert "requires 'artwork_id'" in caught.value.message
    assert caught.value.enumeration["required_parameters"] == ["artwork_id"]


def test_a_parameter_the_action_does_not_take_is_named():
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError) as caught:
        registry.validate(ART_CATALOGUE, action, {"action": "list", "artwork_id": "x"})

    assert "does not take 'artwork_id'" in caught.value.message


def test_a_value_outside_a_parameters_valid_set_is_reported_with_that_set():
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError) as caught:
        registry.validate(ART_CATALOGUE, action, {"action": "list", "status": "archive"})

    assert caught.value.enumeration["valid_values"] == {"status": ["accepted", "archived"]}


def test_a_value_of_the_wrong_type_is_refused_rather_than_coerced():
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError, match="must be an integer"):
        registry.validate(ART_CATALOGUE, action, {"action": "list", "limit": "10"})


def test_a_boolean_is_not_accepted_as_an_integer():
    # bool subclasses int in Python, so an unguarded isinstance check would let
    # `limit=True` through and then behave as `limit=1`.
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError, match="must be an integer"):
        registry.validate(ART_CATALOGUE, action, {"action": "list", "limit": True})


def test_a_value_outside_a_parameters_range_reports_the_bounds():
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError) as caught:
        registry.validate(ART_CATALOGUE, action, {"action": "list", "limit": 500})

    assert caught.value.enumeration["parameter_range"] == {"limit": {"minimum": 1, "maximum": 100}}
    assert "between 1 and 100" in caught.value.message


def test_a_one_sided_range_is_described_by_the_bound_it_has():
    # `offset` declares a minimum and no maximum. Rendering the absent bound
    # reads as a ceiling of null rather than as no ceiling at all — the same
    # reason `help` filters its bounds.
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError) as caught:
        registry.validate(ART_CATALOGUE, action, {"action": "list", "offset": -1})

    assert caught.value.enumeration["parameter_range"] == {"offset": {"minimum": 0}}
    assert "at least 0" in caught.value.message
    assert "None" not in caught.value.message


def test_validated_arguments_come_back_unchanged():
    action = ART_CATALOGUE.action("list")

    validated = registry.validate(ART_CATALOGUE, action, {"action": "list", "status": "accepted", "limit": 5})

    assert validated == {"status": "accepted", "limit": 5}


def test_an_explicit_null_is_treated_as_absent():
    # Clients routinely send every parameter with nulls for the ones they do
    # not mean; treating those as supplied would refuse valid calls.
    action = ART_CATALOGUE.action("list")

    assert registry.validate(ART_CATALOGUE, action, {"action": "list", "status": None}) == {}


def test_an_explicit_null_does_not_satisfy_a_required_parameter():
    action = ART_CATALOGUE.action("get")

    with pytest.raises(ArgumentError, match="requires 'artwork_id'"):
        registry.validate(ART_CATALOGUE, action, {"action": "get", "artwork_id": None})


def test_an_oversized_value_is_truncated_before_being_quoted_back():
    action = ART_CATALOGUE.action("list")

    with pytest.raises(ArgumentError) as caught:
        registry.validate(ART_CATALOGUE, action, {"action": "list", "limit": "x" * 5000})

    assert len(caught.value.message) < 200
