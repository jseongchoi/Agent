from __future__ import annotations

from typing import Any


class ToolValidationError(ValueError):
    pass


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    if schema.get("type") != "object":
        raise ToolValidationError("Tool parameter schema must be an object schema.")

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    additional = bool(schema.get("additionalProperties", False))
    validated = dict(arguments)

    missing = sorted(name for name in required if name not in validated)
    if missing:
        raise ToolValidationError(f"Missing required argument(s): {', '.join(missing)}")

    for name, spec in properties.items():
        if name not in validated and "default" in spec:
            validated[name] = spec["default"]

    if not additional:
        unknown = sorted(name for name in validated if name not in properties)
        if unknown:
            raise ToolValidationError(f"Unknown argument(s): {', '.join(unknown)}")

    for name, value in list(validated.items()):
        if name not in properties:
            continue
        _validate_value(name, value, properties[name])

    return validated


def _validate_value(name: str, value: Any, spec: dict[str, Any]) -> None:
    expected = spec.get("type")
    if expected == "string" and not isinstance(value, str):
        raise ToolValidationError(f"Argument '{name}' must be a string.")
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolValidationError(f"Argument '{name}' must be an integer.")
        _validate_bounds(name, value, spec)
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ToolValidationError(f"Argument '{name}' must be a number.")
        _validate_bounds(name, float(value), spec)
    if expected == "array":
        if not isinstance(value, list):
            raise ToolValidationError(f"Argument '{name}' must be an array.")
        item_spec = spec.get("items")
        if item_spec:
            for index, item in enumerate(value):
                _validate_value(f"{name}[{index}]", item, item_spec)
    if expected == "object" and not isinstance(value, dict):
        raise ToolValidationError(f"Argument '{name}' must be an object.")


def _validate_bounds(name: str, value: float, spec: dict[str, Any]) -> None:
    minimum = spec.get("minimum")
    maximum = spec.get("maximum")
    if minimum is not None and value < float(minimum):
        raise ToolValidationError(f"Argument '{name}' must be >= {minimum}.")
    if maximum is not None and value > float(maximum):
        raise ToolValidationError(f"Argument '{name}' must be <= {maximum}.")
