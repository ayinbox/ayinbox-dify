"""Parsing of Dify tool parameters into API values, with plain error messages."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SPLIT_RE = re.compile(r"[,;\n]+")


class InputError(ValueError):
    """A tool argument the plugin refuses before calling the API."""


def text(params: dict[str, Any], name: str, *, required: bool = False, max_len: int | None = None) -> str | None:
    value = params.get(name)
    if value is None:
        value = ""
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        if required:
            raise InputError(f'"{name}" is required.')
        return None
    if max_len is not None and len(value) > max_len:
        raise InputError(f'"{name}" is longer than {max_len} characters.')
    return value


def integer(params: dict[str, Any], name: str, *, minimum: int, maximum: int, default: int | None = None) -> int | None:
    value = params.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        raise InputError(f'"{name}" must be a whole number.')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InputError(f'"{name}" must be a whole number.') from None
    if number != int(number):
        raise InputError(f'"{name}" must be a whole number.')
    number = int(number)
    if number < minimum or number > maximum:
        raise InputError(f'"{name}" must be between {minimum} and {maximum}.')
    return number


def flag(params: dict[str, Any], name: str) -> bool | None:
    """True, False, or None when the caller left it unset ("any" counts as unset)."""
    value = params.get(name)
    if value is None or isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"", "any"}:
        return None
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    raise InputError(f'"{name}" must be true or false.')


def choice(params: dict[str, Any], name: str, options: set[str]) -> str | None:
    value = text(params, name)
    if value is None or value == "any":
        return None
    if value not in options:
        raise InputError(f'"{name}" must be one of: {", ".join(sorted(options))}.')
    return value


def uuid_value(params: dict[str, Any], name: str, *, required: bool = False) -> str | None:
    value = text(params, name, required=required)
    if value is None:
        return None
    if not _UUID_RE.match(value):
        raise InputError(f'"{name}" must be a UUID such as 11111111-1111-4111-8111-111111111111.')
    return value.lower()


def string_list(params: dict[str, Any], name: str, *, required: bool = False, max_items: int = 1000) -> list[str]:
    raw = params.get(name)
    if isinstance(raw, list):
        items = [str(v).strip() for v in raw]
    else:
        items = [part.strip() for part in _SPLIT_RE.split(str(raw or ""))]
    items = [item for item in items if item]
    if required and not items:
        raise InputError(f'"{name}" needs at least one value.')
    if len(items) > max_items:
        raise InputError(f'"{name}" takes at most {max_items} values.')
    return items


def email_list(params: dict[str, Any], name: str, *, required: bool = False) -> list[str]:
    items = string_list(params, name, required=required, max_items=50)
    for item in items:
        if "@" not in item or " " in item:
            raise InputError(f'"{name}" holds a value that is not an email address: {item}')
    return items


def uuid_list(params: dict[str, Any], name: str) -> list[str]:
    items = string_list(params, name, max_items=100)
    for item in items:
        if not _UUID_RE.match(item):
            raise InputError(f'"{name}" holds a value that is not a UUID: {item}')
    return [item.lower() for item in items]


def json_value(params: dict[str, Any], name: str, kind: type) -> Any:
    raw = params.get(name)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, kind):
        return raw
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise InputError(f'"{name}" must be valid JSON.') from None
    if not isinstance(value, kind):
        expected = "a JSON object" if kind is dict else "a JSON array"
        raise InputError(f'"{name}" must be {expected}.')
    return value


def new_uuid() -> str:
    return str(uuid.uuid4())
