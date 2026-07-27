"""Tool records, and everything generated from them.

One record per action carries its description, its parameters, a worked
example, and its tips. The wire schema, the argument validation, the `help`
output, and the error messages are all derived from that record — so they are
consistent by construction rather than by whoever edits them remembering to
edit all four. Hand-editing any generated artifact is the violation this
module exists to prevent.

The records are declarative and hold no logic. An action record that decides
something is in the wrong file: the decision belongs to a service method, and
the binding between the two lives in `bindings.py`.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

#: Claude Code truncates a tool description at 2 KB. Past that the action menu
#: is cut mid-word and the model is choosing from a list it cannot fully see.
DESCRIPTION_BUDGET_BYTES: Final[int] = 2048

#: The action every tool answers, generated rather than declared so it cannot
#: drift from the schema it documents.
HELP_ACTION: Final[str] = "help"

_JSON_TYPES: Final[Mapping[str, type | tuple[type, ...]]] = {
    "string": str,
    "integer": int,
    "boolean": bool,
}


class RegistryError(RuntimeError):
    """The registry itself is malformed — a defect in this package, not a caller error.

    Raised at import for the structural checks, and from a generator asked to
    describe a record that cannot be described. Never raised in response to
    anything a caller sent: those are `ArgumentError`.
    """


@dataclass(frozen=True, slots=True)
class Param:
    """One argument an action accepts.

    `choices`, `minimum`, and `maximum` are the valid set in machine-readable
    form: they become the JSON Schema constraint, the value the validator
    checks, and the enumeration an error message quotes back.
    """

    name: str
    type: str
    description: str
    required: bool = False
    choices: tuple[str, ...] | None = None
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self) -> None:
        if self.type not in _JSON_TYPES:
            raise RegistryError(f"Param {self.name!r} has unsupported type {self.type!r}.")

    def json_schema(self) -> dict[str, object]:
        schema: dict[str, object] = {"type": self.type, "description": self.description}
        if self.choices is not None:
            schema["enum"] = list(self.choices)
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        return schema


@dataclass(frozen=True, slots=True)
class Action:
    """One operation a tool can be asked to perform."""

    name: str
    description: str
    example: str
    params: tuple[Param, ...] = ()
    tips: tuple[str, ...] = ()

    @property
    def required_params(self) -> tuple[Param, ...]:
        return tuple(param for param in self.params if param.required)

    @property
    def optional_params(self) -> tuple[Param, ...]:
        return tuple(param for param in self.params if not param.required)


@dataclass(frozen=True, slots=True)
class ToolRecord:
    """One MCP tool: a noun, dispatching on a required `action` string.

    `unavailable_note` marks a tool whose name is registered but whose actions
    have not been built. Registering the name from the start is deliberate —
    tool names are a frozen contract, so they are all claimed at once rather
    than appearing one at a time and tempting a rename along the way.
    """

    name: str
    title: str
    summary: str
    read_only: bool
    destructive: bool
    open_world: bool
    actions: tuple[Action, ...] = ()
    unavailable_note: str | None = None
    _by_name: dict[str, Action] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        actions = (*self.actions, self._help_action())
        seen: dict[str, Action] = {}
        for action in actions:
            if action.name in seen:
                raise RegistryError(f"{self.name} declares action {action.name!r} twice.")
            seen[action.name] = action
        self._by_name.update(seen)
        # A tool marked unavailable refuses every action but `help`, so actions
        # declared alongside the note are unreachable — the half-finished state
        # of flipping a tool from unbuilt to built. Silent otherwise: the tool
        # answers "not available yet" to the very actions it advertises.
        if self.unavailable_note is not None and self.actions:
            raise RegistryError(
                f"{self.name} declares actions {sorted(a.name for a in self.actions)} but is still marked unavailable; "
                "clear unavailable_note when the actions are wired."
            )
        self._check_params_agree()

    def _help_action(self) -> Action:
        return Action(
            name=HELP_ACTION,
            description="List every action this tool takes, with its parameters, an example, and tips.",
            example=f"{self.name}(action='help')",
            tips=("help never reads the catalogue, so it works even when nothing has been curated yet.",),
        )

    def _check_params_agree(self) -> None:
        """Refuse a registry where one parameter name means two things.

        Every action's parameters are flattened onto a single wire schema, so
        two actions declaring `limit` as an integer and a string would produce
        a schema that lies about one of them. Caught at import because the
        alternative is a client discovering it.
        """
        declared: dict[str, Param] = {}
        for action in self._by_name.values():
            for param in action.params:
                previous = declared.get(param.name)
                if previous is None:
                    declared[param.name] = param
                    continue
                # Bounds are compared alongside type and choices because
                # `all_params()` publishes the first declaration it sees. Two
                # actions declaring `limit` with different maxima would ship a
                # schema stating one action's ceiling as if it governed both,
                # while per-action validation quietly enforced the other.
                if (previous.type, previous.choices, previous.minimum, previous.maximum) != (
                    param.type,
                    param.choices,
                    param.minimum,
                    param.maximum,
                ):
                    raise RegistryError(
                        f"{self.name} declares {param.name!r} inconsistently: "
                        f"{previous.type}/{previous.choices}/{previous.minimum}-{previous.maximum} then "
                        f"{param.type}/{param.choices}/{param.minimum}-{param.maximum}."
                    )

    @property
    def action_names(self) -> tuple[str, ...]:
        return tuple(self._by_name)

    @property
    def available(self) -> bool:
        """False while the tool answers `help` and nothing else."""
        return self.unavailable_note is None

    def action(self, name: str) -> Action | None:
        return self._by_name.get(name)

    def all_params(self) -> tuple[Param, ...]:
        """Every parameter any action takes, each named once."""
        flattened: dict[str, Param] = {}
        for action in self._by_name.values():
            for param in action.params:
                flattened.setdefault(param.name, param)
        return tuple(flattened.values())


def description(tool: ToolRecord) -> str:
    """The tool description a client sees: a summary and the action menu.

    Depth lives behind `action='help'` rather than here, because this text is
    truncated at 2 KB by the client and a truncated menu is worse than a short
    one.
    """
    lines = [tool.summary, "", "Actions:"]
    lines.extend(f"  {name} — {tool.action(name).description}" for name in tool.action_names)  # type: ignore[union-attr]
    lines.append("")
    if tool.unavailable_note is None:
        lines.append(f"Call with action='<name>' plus that action's parameters. {tool.name}(action='help') shows them.")
    else:
        lines.append(tool.unavailable_note)
    return "\n".join(lines)


def input_schema(tool: ToolRecord) -> dict[str, object]:
    """The flattened wire schema: `action` required, everything else optional.

    A nested `params: {...}` envelope is hostile to a model writing the call,
    and a wire-level discriminated union would force callers to widen to a
    plain string anyway because the valid set is runtime data. So the union of
    every action's parameters is flattened here and checked per action at
    dispatch.
    """
    properties: dict[str, object] = {
        "action": {
            "type": "string",
            "enum": list(tool.action_names),
            "description": "Which operation to perform. Required.",
        }
    }
    for param in tool.all_params():
        properties[param.name] = param.json_schema()
    return {"type": "object", "properties": properties, "required": ["action"]}


def help_payload(tool: ToolRecord) -> dict[str, object]:
    """The `help` result: the same records the schema was generated from."""
    return {
        "tool": tool.name,
        "title": tool.title,
        "summary": tool.summary,
        "available": tool.available,
        "note": tool.unavailable_note,
        "actions": [_action_help(tool.action(name)) for name in tool.action_names],  # type: ignore[arg-type]
    }


def _action_help(action: Action) -> dict[str, object]:
    return {
        "action": action.name,
        "description": action.description,
        "required_parameters": [_param_help(param) for param in action.required_params],
        "optional_parameters": [_param_help(param) for param in action.optional_params],
        "example": action.example,
        "tips": list(action.tips),
    }


def _param_help(param: Param) -> dict[str, object]:
    described: dict[str, object] = {
        "name": param.name,
        "type": param.type,
        "description": param.description,
    }
    if param.choices is not None:
        described["valid_values"] = list(param.choices)
    bounds = _bounds(param)
    if bounds:
        described["range"] = bounds
    return described


def _bounds(param: Param) -> dict[str, int]:
    """Only the bounds that exist.

    A one-sided range reported as `{"minimum": 0, "maximum": null}` reads as a
    bound of null rather than as no upper bound at all. Shared by `help` and by
    the range error, so the two cannot describe the same parameter differently.
    """
    return {name: value for name, value in (("minimum", param.minimum), ("maximum", param.maximum)) if value is not None}


def _bounds_phrase(param: Param) -> str:
    """The range in words, for whichever bounds the parameter actually has.

    Refuses the no-bounds case rather than falling through to it: the fall-through
    would render "at most None", which is the exact string this helper exists to
    prevent, and it would come back the first time anything but the range check
    calls this.
    """
    if param.minimum is not None and param.maximum is not None:
        return f"between {param.minimum} and {param.maximum}"
    if param.minimum is not None:
        return f"at least {param.minimum}"
    if param.maximum is not None:
        return f"at most {param.maximum}"
    raise RegistryError(f"Param {param.name!r} has no bounds to describe.")


class ArgumentError(Exception):
    """Arguments that do not fit the action, described so a caller can fix it.

    Carries the enumerated valid set alongside the message: every error on
    this surface names what was wrong *and* what would have been right, and
    the only way to guarantee that is to make the valid set part of the
    exception rather than something each call site remembers to add.
    """

    def __init__(self, message: str, *, enumeration: Mapping[str, object] | None = None, example: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.enumeration: Mapping[str, object] = dict(enumeration or {})
        self.example = example


def resolve_action(tool: ToolRecord, arguments: Mapping[str, object]) -> Action:
    """Pick the action named by the arguments, or explain why none matched."""
    raw = arguments.get("action")
    valid = {"valid_actions": list(tool.action_names)}
    help_example = f"{tool.name}(action='help')"

    if raw is None:
        raise ArgumentError(f"{tool.name} requires an 'action' parameter.", enumeration=valid, example=help_example)
    if not isinstance(raw, str):
        raise ArgumentError(f"'action' must be a string, got {_render(raw)}.", enumeration=valid, example=help_example)

    # Checked before the action lookup, not after. An unbuilt tool declares no
    # actions, so every real action name would otherwise come back as "unknown
    # action" — telling a caller the action does not exist when the truth is
    # that the tool does not serve it yet.
    if not tool.available and raw != HELP_ACTION:
        raise ArgumentError(
            f"{tool.name}(action={raw!r}) is not available yet — this tool answers only action='help'.",
            enumeration=valid,
            example=help_example,
        )

    action = tool.action(raw)
    if action is None:
        raise ArgumentError(f"Unknown action: {raw!r}", enumeration=valid, example=help_example)
    return action


def validate(tool: ToolRecord, action: Action, arguments: Mapping[str, object]) -> dict[str, object]:
    """Check the arguments against the action's parameters and return them.

    Values come back unchanged; this validates rather than coerces, so a
    caller that sent `"10"` for an integer is told so instead of having it
    quietly accepted and a different caller's `10` behaving identically.
    """
    declared = {param.name: param for param in action.params}
    supplied = {name: value for name, value in arguments.items() if name != "action"}

    unknown = sorted(set(supplied) - set(declared))
    if unknown:
        raise ArgumentError(
            f"{tool.name}(action={action.name!r}) does not take {_english_list(unknown)}.",
            enumeration=_parameter_enumeration(action),
            example=action.example,
        )

    missing = sorted(param.name for param in action.required_params if supplied.get(param.name) is None)
    if missing:
        raise ArgumentError(
            f"{tool.name}(action={action.name!r}) requires {_english_list(missing)}.",
            enumeration=_parameter_enumeration(action),
            example=action.example,
        )

    for name, value in supplied.items():
        if value is not None:
            _check_value(declared[name], value, action)
    return {name: value for name, value in supplied.items() if value is not None}


def _check_value(param: Param, value: object, action: Action) -> None:
    expected = _JSON_TYPES[param.type]
    # bool is a subclass of int in Python; an integer parameter given `true`
    # would otherwise pass and then behave as 1.
    if param.type == "integer" and isinstance(value, bool):
        raise ArgumentError(
            f"Parameter {param.name!r} must be an integer, got {_render(value)}.",
            enumeration={"parameter_types": {param.name: param.type}},
            example=action.example,
        )
    if not isinstance(value, expected):
        raise ArgumentError(
            f"Parameter {param.name!r} must be {_article(param.type)}, got {_render(value)}.",
            enumeration={"parameter_types": {param.name: param.type}},
            example=action.example,
        )
    if param.choices is not None and value not in param.choices:
        raise ArgumentError(
            f"Invalid value for {param.name!r}: {_render(value)}.",
            enumeration={"valid_values": {param.name: list(param.choices)}},
            example=action.example,
        )
    if isinstance(value, int) and (
        (param.minimum is not None and value < param.minimum) or (param.maximum is not None and value > param.maximum)
    ):
        raise ArgumentError(
            f"Parameter {param.name!r} must be {_bounds_phrase(param)}, got {value}.",
            enumeration={"parameter_range": {param.name: _bounds(param)}},
            example=action.example,
        )


def _parameter_enumeration(action: Action) -> dict[str, object]:
    return {
        "required_parameters": [param.name for param in action.required_params],
        "optional_parameters": [param.name for param in action.optional_params],
    }


def _english_list(names: Sequence[str]) -> str:
    quoted = [f"{name!r}" for name in names]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _article(json_type: str) -> str:
    return f"an {json_type}" if json_type[0] in "aeiou" else f"a {json_type}"


def _render(value: object) -> str:
    """Quote a caller's value back safely, without letting a huge one through."""
    text = json.dumps(value) if not isinstance(value, str) else repr(value)
    return text if len(text) <= 60 else f"{text[:57]}..."
