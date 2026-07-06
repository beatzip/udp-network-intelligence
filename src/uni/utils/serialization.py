"""Shared serialization utilities for model dataclasses.

Provides JSON-safe serialization/deserialization helpers used by all
domain models across the application.
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar, get_type_hints

T = TypeVar("T")


def enum_to_value(obj: Any) -> Any:
    """Convert an Enum instance to its .value for JSON serialization.

    Args:
        obj: Object to convert.

    Returns:
        Enum value if obj is an Enum, otherwise obj unchanged.
    """
    if isinstance(obj, Enum):
        return obj.value
    return obj


def model_to_dict(instance: Any, *, exclude_none: bool = False) -> dict[str, Any]:
    """Serialize a dataclass instance to a JSON-compatible dictionary.

    Handles nested dataclasses, Enums, datetime objects, bytes, and lists/dicts
    containing any of the above.

    Args:
        instance: Dataclass instance to serialize.
        exclude_none: If True, omit keys with None values.

    Returns:
        JSON-serializable dictionary.
    """
    result: dict[str, Any] = {}
    for f in fields(instance):
        value = getattr(instance, f.name)
        converted = _convert_value(value)
        if exclude_none and converted is None:
            continue
        result[f.name] = converted
    return result


def _convert_value(value: Any) -> Any:
    """Recursively convert a value to a JSON-safe representation.

    Args:
        value: Value to convert.

    Returns:
        JSON-safe value.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return list(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_convert_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _convert_value(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return model_to_dict(value)
    if isinstance(value, tuple):
        return [_convert_value(item) for item in value]
    if isinstance(value, set):
        return [_convert_value(item) for item in sorted(value, key=str)]
    return str(value)


def _restore_value(value: Any, expected_type: Any) -> Any:
    """Restore a value from its JSON representation to the expected type.

    Args:
        value: Raw value from JSON/dict.
        expected_type: The target type annotation.

    Returns:
        Restored value.
    """
    if value is None:
        return None

    # Handle Optional[X] (Union[X, None])
    origin = getattr(expected_type, "__origin__", None)
    args = getattr(expected_type, "__args__", ())

    if origin is type(None):
        return None

    # Union types (e.g., str | None, float | None)
    if origin is not None and hasattr(origin, "__union_params__"):
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _restore_value(value, non_none[0])
        return value

    # Handle list[X]
    if origin is list and args:
        inner = args[0]
        if isinstance(value, list):
            return [_restore_value(item, inner) for item in value]
        return value

    # Handle dict[K, V]
    if origin is dict and len(args) == 2:
        _key_type, val_type = args
        if isinstance(value, dict):
            return {k: _restore_value(v, val_type) for k, v in value.items()}
        return value

    # Handle tuple[X, ...]
    if origin is tuple:
        if isinstance(value, list):
            if args and args[-1] is Ellipsis:
                return tuple(_restore_value(item, args[0]) for item in value)
            return tuple(
                _restore_value(item, args[i]) if i < len(args) else item
                for i, item in enumerate(value)
            )
        return value

    # Enum
    if isinstance(expected_type, type) and issubclass(expected_type, Enum):
        if isinstance(value, expected_type):
            return value
        try:
            return expected_type(value)
        except (ValueError, KeyError):
            return value

    # datetime
    if expected_type is datetime:
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        if isinstance(value, datetime):
            return value
        return value

    # bytes
    if expected_type is bytes:
        if isinstance(value, list):
            return bytes(value)
        if isinstance(value, str):
            return value.encode("utf-8")
        return value

    # Nested dataclass
    if hasattr(expected_type, "__dataclass_fields__"):
        if isinstance(value, dict):
            return model_from_dict(expected_type, value)  # type: ignore[arg-type]
        return value

    # int, float, str, bool
    if expected_type in (int, float, str, bool):
        try:
            return expected_type(value)
        except (ValueError, TypeError):
            return value

    return value


def model_from_dict(cls: type[T], data: dict[str, Any]) -> T:
    """Deserialize a dictionary into a dataclass instance.

    Handles nested dataclasses, Enums, datetime, bytes, and all
    standard Python types.

    Args:
        cls: Target dataclass type.
        data: Source dictionary.

    Returns:
        Populated dataclass instance.

    Raises:
        TypeError: If cls is not a dataclass.
        KeyError: If required fields are missing.
    """
    if not hasattr(cls, "__dataclass_fields__"):
        raise TypeError(f"{cls.__name__} is not a dataclass")

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}

    for f in fields(cls):
        if f.name not in data:
            continue
        raw = data[f.name]
        target_type = hints.get(f.name, object)
        kwargs[f.name] = _restore_value(raw, target_type)

    return cls(**kwargs)  # type: ignore[call-arg]


def to_json(
    instance: Any,
    *,
    indent: int | None = None,
    exclude_none: bool = False,
) -> str:
    """Serialize a dataclass instance to a JSON string.

    Args:
        instance: Dataclass instance to serialize.
        indent: JSON indentation level. None for compact output.
        exclude_none: If True, omit keys with None values.

    Returns:
        JSON string.
    """
    data = model_to_dict(instance, exclude_none=exclude_none)
    return json.dumps(data, indent=indent, ensure_ascii=False)


def from_json(cls: type[T], json_str: str) -> T:
    """Deserialize a JSON string into a dataclass instance.

    Args:
        cls: Target dataclass type.
        json_str: JSON string.

    Returns:
        Populated dataclass instance.
    """
    data = json.loads(json_str)
    return model_from_dict(cls, data)
