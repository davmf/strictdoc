"""
Declarations of project actions: commands that a project lets the web UI run.

A project lists its actions in strictdoc_config.py. Each action has a fixed
argv and typed parameters. The server turns the values of a submitted form
into extra argv items. It never passes these values through a shell.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

ParameterValue = Union[str, int, float, bool]

HANDLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ProjectActionParameterKind:
    CHOICE = "choice"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"

    ALL = (CHOICE, INTEGER, FLOAT, BOOLEAN, STRING)


@dataclass
class ProjectActionParameter:
    """
    A typed command line option of an action.

    name is the form field name, in snake_case. flag is the option that
    precedes the value, e.g. "--scenario". A boolean parameter adds only its
    flag, and only when the value is true.
    """

    name: str
    flag: str
    kind: str
    title: Optional[str] = None
    default: Optional[ParameterValue] = None
    choices: List[str] = field(default_factory=list)
    required: bool = False

    def get_title(self) -> str:
        if self.title is not None:
            return self.title
        return self.name.replace("_", " ").capitalize()

    def get_default_as_text(self) -> str:
        if self.default is None:
            return ""
        if isinstance(self.default, bool):
            return "true" if self.default else ""
        return str(self.default)


@dataclass
class ProjectActionSysMLBinding:
    """
    Offers an action on the page of each matching SysML design element.

    An element matches when its keyword is element_kind (e.g. "part" for a
    usage, "part def" for a definition) and its type or one of the types it
    specialises is named specializes. The element name becomes the value of
    the parameter named parameter.
    """

    element_kind: str
    specializes: str
    parameter: str


@dataclass
class ProjectAction:
    handle: str
    title: str
    argv: List[str]
    description: Optional[str] = None
    parameters: List[ProjectActionParameter] = field(default_factory=list)
    # Globs, relative to the project root, of the files that the action
    # writes. The run screen shows the files that changed during a run.
    outputs: List[str] = field(default_factory=list)
    sysml_binding: Optional[ProjectActionSysMLBinding] = None

    def get_parameter(self, name: str) -> Optional[ProjectActionParameter]:
        for parameter_ in self.parameters:
            if parameter_.name == name:
                return parameter_
        return None


class ProjectActionValidationError(Exception):
    def __init__(self, errors: Dict[str, str]) -> None:
        super().__init__(", ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors: Dict[str, str] = errors


def validate_project_actions(project_actions: List[ProjectAction]) -> None:
    """Raise ValueError if a declaration in the project config is invalid."""

    if not isinstance(project_actions, list):
        raise ValueError("config: project_actions: must be a list.")
    seen_handles: List[str] = []
    for action_ in project_actions:
        if not isinstance(action_, ProjectAction):
            raise ValueError(
                "config: project_actions: each item must be a ProjectAction: "
                f"{action_!r}."
            )
        prefix = f"config: project_actions: {action_.handle}"
        if HANDLE_PATTERN.match(action_.handle) is None:
            raise ValueError(f"{prefix}: handle must be snake_case.")
        if action_.handle in seen_handles:
            raise ValueError(f"{prefix}: duplicate handle.")
        seen_handles.append(action_.handle)
        if (
            not isinstance(action_.argv, list)
            or len(action_.argv) == 0
            or not all(isinstance(item_, str) for item_ in action_.argv)
        ):
            raise ValueError(f"{prefix}: argv must be a non-empty list of str.")
        seen_names: List[str] = []
        for parameter_ in action_.parameters:
            _validate_parameter(prefix, parameter_, seen_names)
        if action_.sysml_binding is not None:
            if action_.get_parameter(action_.sysml_binding.parameter) is None:
                raise ValueError(
                    f"{prefix}: sysml_binding: unknown parameter: "
                    f"{action_.sysml_binding.parameter}."
                )


def build_argv(action: ProjectAction, form_values: Dict[str, str]) -> List[str]:
    """
    Return the argv of a run from the values of a submitted form.

    Raise ProjectActionValidationError with one message per invalid field.
    """

    errors: Dict[str, str] = {}
    argv: List[str] = list(action.argv)
    for parameter_ in action.parameters:
        raw_value = form_values.get(parameter_.name, "").strip()
        if parameter_.kind == ProjectActionParameterKind.BOOLEAN:
            if raw_value in ("true", "on", "1"):
                argv.append(parameter_.flag)
            elif raw_value not in ("", "false", "off", "0"):
                errors[parameter_.name] = "Must be true or false."
            continue
        if len(raw_value) == 0:
            if parameter_.required:
                errors[parameter_.name] = "A value is required."
            continue
        error = _check_value(parameter_, raw_value)
        if error is not None:
            errors[parameter_.name] = error
            continue
        argv.extend([parameter_.flag, raw_value])
    if len(errors) > 0:
        raise ProjectActionValidationError(errors)
    return argv


def _validate_parameter(
    prefix: str, parameter: ProjectActionParameter, seen_names: List[str]
) -> None:
    if not isinstance(parameter, ProjectActionParameter):
        raise ValueError(
            f"{prefix}: each parameter must be a ProjectActionParameter: "
            f"{parameter!r}."
        )
    if HANDLE_PATTERN.match(parameter.name) is None:
        raise ValueError(
            f"{prefix}: parameter {parameter.name}: name must be snake_case."
        )
    if parameter.name in seen_names:
        raise ValueError(f"{prefix}: duplicate parameter: {parameter.name}.")
    seen_names.append(parameter.name)
    if parameter.kind not in ProjectActionParameterKind.ALL:
        raise ValueError(
            f"{prefix}: parameter {parameter.name}: unknown kind: "
            f"{parameter.kind}. Expected one of: "
            f"{', '.join(ProjectActionParameterKind.ALL)}."
        )
    if len(parameter.flag) == 0:
        raise ValueError(
            f"{prefix}: parameter {parameter.name}: flag must not be empty."
        )
    if parameter.kind == ProjectActionParameterKind.CHOICE:
        if len(parameter.choices) == 0:
            raise ValueError(
                f"{prefix}: parameter {parameter.name}: a choice parameter "
                "needs choices."
            )
    if parameter.default is not None and not isinstance(
        parameter.default, bool
    ):
        error = _check_value(parameter, str(parameter.default))
        if error is not None:
            raise ValueError(
                f"{prefix}: parameter {parameter.name}: default: {error}"
            )


def _check_value(
    parameter: ProjectActionParameter, value: str
) -> Optional[str]:
    if parameter.kind == ProjectActionParameterKind.CHOICE:
        if value not in parameter.choices:
            return f"Must be one of: {', '.join(parameter.choices)}."
    elif parameter.kind == ProjectActionParameterKind.INTEGER:
        try:
            int(value)
        except ValueError:
            return "Must be an integer."
    elif parameter.kind == ProjectActionParameterKind.FLOAT:
        try:
            float(value)
        except ValueError:
            return "Must be a number."
    # A value that starts with "-" could be read as another option.
    if value.startswith("-") and parameter.kind in (
        ProjectActionParameterKind.CHOICE,
        ProjectActionParameterKind.STRING,
    ):
        return "Must not start with '-'."
    return None
